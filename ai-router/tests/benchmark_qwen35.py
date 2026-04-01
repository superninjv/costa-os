#!/usr/bin/env python3
"""Qwen 3.5 Model Benchmark — Raw capability testing across all model sizes.

Calls Ollama directly (bypassing the costa-ai router) to measure each model's
raw quality, speed, thinking mode impact, and GPU idle behavior.

Usage:
    # Benchmark a single model
    python3 benchmark_qwen35.py --model qwen3.5:4b

    # Benchmark all qwen3.5 models sequentially
    python3 benchmark_qwen35.py --all

    # Include thinking mode comparison (slower, 20 extra prompts)
    python3 benchmark_qwen35.py --model qwen3.5:9b --test-thinking

    # Generate markdown comparison table from results
    python3 benchmark_qwen35.py --summarize

Output: JSON per model at ~/Downloads/qwen35-bench/qwen35-{size}.json
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from statistics import mean, median

# ─── Add parent dir so we can import from ai-router ──────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELS = ["qwen3.5:0.8b", "qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b"]
OUTPUT_DIR = Path.home() / "Downloads" / "qwen35-bench"
GPU_BUSY_PATH = "/sys/class/drm/card1/device/gpu_busy_percent"

SYSTEM_PROMPT = """You are Costa AI, a helpful assistant running on Arch Linux with Hyprland.
Answer concisely and accurately. If system context is provided, use it to answer.
Do not say "I don't know" if you can reason about the answer from context."""


# ─── Types ────────────────────────────────────────────────────

@dataclass
class PromptResult:
    prompt: str
    category: str
    response: str
    quality_score: float
    failure_type: str  # "none", "refused", "hallucinated", "incomplete", "wrong"
    eval_tokens: int
    eval_tok_per_sec: float
    prompt_tokens: int
    prompt_tok_per_sec: float
    total_ms: int
    thinking_response: str = ""
    thinking_quality: float = 0.0
    thinking_ms: int = 0


@dataclass
class ModelReport:
    model: str
    timestamp: str
    gpu_idle_samples: list[int] = field(default_factory=list)
    gpu_idle_avg: float = 0.0
    gpu_idle_max: int = 0
    results: list[dict] = field(default_factory=list)
    thinking_results: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    per_category: dict = field(default_factory=dict)


# ─── Quality scoring (matches test_harness.py logic) ─────────

def score_quality(response: str, keywords: list[str], anti_keywords: list[str]) -> float:
    if not response or not response.strip():
        return 0.0
    resp_lower = response.lower()
    score = 0.5
    if keywords:
        hits = sum(1 for kw in keywords if kw.lower() in resp_lower)
        score += 0.5 * (hits / len(keywords))
    if anti_keywords:
        anti_hits = sum(1 for kw in anti_keywords if kw.lower() in resp_lower)
        if anti_hits > 0:
            score -= 0.3 * (anti_hits / len(anti_keywords))
    return max(0.0, min(1.0, score))


def classify_failure(response: str, quality: float, keywords: list[str]) -> str:
    if quality >= 0.3:
        return "none"
    if not response or len(response.strip()) < 20:
        return "incomplete"
    resp_lower = response.lower()
    idk_patterns = ["i don't know", "i cannot", "i'm not sure", "unable to",
                     "don't have access", "as an ai", "my knowledge cutoff"]
    if any(p in resp_lower for p in idk_patterns):
        return "refused"
    if keywords:
        hits = sum(1 for kw in keywords if kw.lower() in resp_lower)
        if hits == 0:
            return "wrong"
    return "hallucinated"


# ─── Ollama query ─────────────────────────────────────────────

def query_ollama(model: str, prompt: str, system: str = SYSTEM_PROMPT,
                 think: bool = False, num_predict: int = 2048,
                 num_ctx: int = 8192, timeout: int = 180) -> dict:
    """Query Ollama directly and return the full response dict."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "think": think,
        "options": {"num_predict": num_predict, "num_ctx": num_ctx},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {"error": str(e), "response": "", "eval_count": 0,
                "eval_duration": 1, "prompt_eval_count": 0,
                "prompt_eval_duration": 1, "total_duration": 0}


def unload_model(model: str):
    """Unload a model from VRAM."""
    payload = json.dumps({"model": model, "keep_alive": 0}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception:
        pass


def warm_model(model: str):
    """Load model into VRAM without generating."""
    payload = json.dumps({"model": model, "prompt": "", "keep_alive": "30m"}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except Exception:
        pass


# ─── GPU monitoring ───────────────────────────────────────────

def sample_gpu_busy(duration_s: int = 15) -> list[int]:
    """Sample gpu_busy_percent over duration, return list of readings."""
    samples = []
    # Try multiple paths
    gpu_path = None
    for p in [GPU_BUSY_PATH, "/sys/class/drm/card0/device/gpu_busy_percent"]:
        if os.path.exists(p):
            gpu_path = p
            break
    if not gpu_path:
        return []
    for _ in range(duration_s):
        try:
            with open(gpu_path) as f:
                samples.append(int(f.read().strip()))
        except (IOError, ValueError):
            pass
        time.sleep(1)
    return samples


# ─── Benchmark runner ─────────────────────────────────────────

def load_prompts(path: str | None = None) -> list[dict]:
    """Load test prompts from JSON file."""
    if path is None:
        path = str(Path(__file__).parent / "prompts_100.json")
    with open(path) as f:
        return json.load(f)


def benchmark_model(model: str, prompts: list[dict],
                    test_thinking: bool = False,
                    verbose: bool = False,
                    num_predict: int = 2048,
                    num_ctx: int = 8192) -> ModelReport:
    """Run full benchmark on a single model."""
    report = ModelReport(model=model, timestamp=datetime.now().isoformat())

    # ── Filter to local-answerable prompts ────────────────────
    # We test all prompts to see what each model CAN handle, but skip
    # meta/window_manager since those are handled by the router, not the model
    test_prompts = [p for p in prompts
                    if p["expected_route"] not in ("meta", "window_manager")]

    print(f"\n{'='*60}")
    print(f"  Benchmarking: {model}")
    print(f"  Prompts: {len(test_prompts)} (skipping meta/window_manager)")
    print(f"  Token budget: num_predict={num_predict}, num_ctx={num_ctx}")
    print(f"{'='*60}")

    # ── Step 1: Load model ────────────────────────────────────
    print(f"  Loading model...", end=" ", flush=True)
    warm_model(model)
    print("done")

    # ── Step 2: GPU idle check ────────────────────────────────
    print(f"  Sampling GPU idle for 15s...", end=" ", flush=True)
    report.gpu_idle_samples = sample_gpu_busy(15)
    if report.gpu_idle_samples:
        report.gpu_idle_avg = round(mean(report.gpu_idle_samples), 1)
        report.gpu_idle_max = max(report.gpu_idle_samples)
        status = "PASS" if report.gpu_idle_avg < 20 else "FAIL"
        print(f"avg={report.gpu_idle_avg}% max={report.gpu_idle_max}% [{status}]")
    else:
        print("no GPU sysfs found")

    # ── Step 3: Run prompts ───────────────────────────────────
    print(f"\n  Running {len(test_prompts)} prompts:")
    results = []

    for i, p in enumerate(test_prompts, 1):
        prompt_text = p["prompt"]
        keywords = p.get("quality_keywords", [])
        anti_kw = p.get("anti_keywords", [])
        category = p.get("category", "unknown")

        resp = query_ollama(model, prompt_text, num_predict=num_predict, num_ctx=num_ctx)
        response_text = resp.get("response", "")

        # Parse metrics
        eval_count = resp.get("eval_count", 0)
        eval_dur = resp.get("eval_duration", 1)
        prompt_count = resp.get("prompt_eval_count", 0)
        prompt_dur = resp.get("prompt_eval_duration", 1)
        total_dur = resp.get("total_duration", 0)

        quality = round(score_quality(response_text, keywords, anti_kw), 3)
        failure = classify_failure(response_text, quality, keywords)

        result = PromptResult(
            prompt=prompt_text,
            category=category,
            response=response_text[:2000],
            quality_score=quality,
            failure_type=failure,
            eval_tokens=eval_count,
            eval_tok_per_sec=round(eval_count / (eval_dur / 1e9), 1) if eval_dur > 0 else 0,
            prompt_tokens=prompt_count,
            prompt_tok_per_sec=round(prompt_count / (prompt_dur / 1e9), 1) if prompt_dur > 0 else 0,
            total_ms=int(total_dur / 1e6),
        )
        results.append(result)

        # Progress
        marker = "." if quality >= 0.3 else "X"
        if verbose:
            print(f"    [{i:3d}/{len(test_prompts)}] q={quality:.2f} {result.eval_tok_per_sec:5.1f}t/s "
                  f"{result.total_ms:5d}ms [{failure:>12}] {prompt_text[:40]}")
        else:
            print(marker, end="", flush=True)
            if i % 40 == 0:
                print(f" [{i}/{len(test_prompts)}]")

    if not verbose:
        print(f" [{len(test_prompts)}/{len(test_prompts)}]")

    report.results = [asdict(r) for r in results]

    # ── Step 4: Thinking mode comparison (optional) ───────────
    if test_thinking:
        thinking_categories = {"deep_knowledge", "code_write"}
        thinking_prompts = [p for p in test_prompts
                           if p.get("category") in thinking_categories][:20]

        if thinking_prompts:
            print(f"\n  Thinking mode test ({len(thinking_prompts)} prompts):")
            thinking_results = []

            for i, p in enumerate(thinking_prompts, 1):
                resp = query_ollama(model, p["prompt"], think=True, num_predict=num_predict, num_ctx=num_ctx)
                response_text = resp.get("response", "")
                quality = round(score_quality(response_text,
                                             p.get("quality_keywords", []),
                                             p.get("anti_keywords", [])), 3)
                total_ms = int(resp.get("total_duration", 0) / 1e6)

                # Find matching non-thinking result
                base_result = next((r for r in results if r.prompt == p["prompt"]), None)
                base_quality = base_result.quality_score if base_result else 0
                base_ms = base_result.total_ms if base_result else 0

                thinking_results.append({
                    "prompt": p["prompt"],
                    "category": p.get("category"),
                    "base_quality": base_quality,
                    "thinking_quality": quality,
                    "quality_delta": round(quality - base_quality, 3),
                    "base_ms": base_ms,
                    "thinking_ms": total_ms,
                    "latency_ratio": round(total_ms / max(base_ms, 1), 2),
                })

                delta_str = f"{quality - base_quality:+.3f}"
                print(f"    [{i:2d}/{len(thinking_prompts)}] base={base_quality:.2f} think={quality:.2f} "
                      f"({delta_str}) {total_ms}ms  {p['prompt'][:40]}")

            report.thinking_results = thinking_results

    # ── Step 5: Compute summary ───────────────────────────────
    qualities = [r.quality_score for r in results]
    latencies = [r.total_ms for r in results]
    tok_speeds = [r.eval_tok_per_sec for r in results if r.eval_tok_per_sec > 0]
    prompt_speeds = [r.prompt_tok_per_sec for r in results if r.prompt_tok_per_sec > 0]
    failures = [r for r in results if r.failure_type != "none"]

    sorted_lat = sorted(latencies)
    p95_idx = int(len(sorted_lat) * 0.95)

    report.summary = {
        "model": model,
        "total_prompts": len(results),
        "avg_quality": round(mean(qualities), 3),
        "median_quality": round(median(qualities), 3),
        "min_quality": round(min(qualities), 3),
        "max_quality": round(max(qualities), 3),
        "quality_above_0.7": sum(1 for q in qualities if q >= 0.7),
        "quality_above_0.5": sum(1 for q in qualities if q >= 0.5),
        "quality_below_0.3": sum(1 for q in qualities if q < 0.3),
        "avg_latency_ms": int(mean(latencies)),
        "median_latency_ms": int(median(latencies)),
        "p95_latency_ms": sorted_lat[p95_idx] if sorted_lat else 0,
        "avg_gen_tok_s": round(mean(tok_speeds), 1) if tok_speeds else 0,
        "avg_prompt_tok_s": round(mean(prompt_speeds), 1) if prompt_speeds else 0,
        "failure_count": len(failures),
        "failure_breakdown": {
            "refused": sum(1 for r in results if r.failure_type == "refused"),
            "hallucinated": sum(1 for r in results if r.failure_type == "hallucinated"),
            "incomplete": sum(1 for r in results if r.failure_type == "incomplete"),
            "wrong": sum(1 for r in results if r.failure_type == "wrong"),
        },
        "gpu_idle_avg": report.gpu_idle_avg,
        "gpu_idle_max": report.gpu_idle_max,
    }

    # Thinking mode summary
    if report.thinking_results:
        deltas = [r["quality_delta"] for r in report.thinking_results]
        report.summary["thinking_avg_delta"] = round(mean(deltas), 3)
        report.summary["thinking_improved"] = sum(1 for d in deltas if d > 0.05)
        report.summary["thinking_degraded"] = sum(1 for d in deltas if d < -0.05)
        report.summary["thinking_neutral"] = sum(1 for d in deltas if -0.05 <= d <= 0.05)

    # Per-category breakdown
    categories = set(r.category for r in results)
    for cat in sorted(categories):
        cat_results = [r for r in results if r.category == cat]
        cat_qualities = [r.quality_score for r in cat_results]
        cat_latencies = [r.total_ms for r in cat_results]
        report.per_category[cat] = {
            "count": len(cat_results),
            "avg_quality": round(mean(cat_qualities), 3),
            "min_quality": round(min(cat_qualities), 3),
            "avg_latency_ms": int(mean(cat_latencies)),
            "failures": sum(1 for r in cat_results if r.failure_type != "none"),
        }

    return report


def print_summary(report: ModelReport):
    """Print a formatted summary of benchmark results."""
    s = report.summary
    print(f"\n{'='*60}")
    print(f"  RESULTS: {report.model}")
    print(f"{'='*60}")
    print(f"  Avg Quality:       {s['avg_quality']:.3f}  (median: {s['median_quality']:.3f})")
    print(f"  Quality >= 0.7:    {s['quality_above_0.7']}/{s['total_prompts']}")
    print(f"  Quality >= 0.5:    {s['quality_above_0.5']}/{s['total_prompts']}")
    print(f"  Quality < 0.3:     {s['quality_below_0.3']}/{s['total_prompts']}")
    print(f"  Avg Gen Speed:     {s['avg_gen_tok_s']} t/s")
    print(f"  Avg Prompt Speed:  {s['avg_prompt_tok_s']} t/s")
    print(f"  Avg Latency:       {s['avg_latency_ms']}ms  (p95: {s['p95_latency_ms']}ms)")
    print(f"  GPU Idle:          {s['gpu_idle_avg']}% avg, {s['gpu_idle_max']}% max")
    print(f"  Failures:          {s['failure_count']} "
          f"(refused={s['failure_breakdown']['refused']}, "
          f"wrong={s['failure_breakdown']['wrong']}, "
          f"incomplete={s['failure_breakdown']['incomplete']}, "
          f"hallucinated={s['failure_breakdown']['hallucinated']})")

    if "thinking_avg_delta" in s:
        print(f"\n  Thinking Mode:")
        print(f"    Avg quality delta: {s['thinking_avg_delta']:+.3f}")
        print(f"    Improved: {s['thinking_improved']}, "
              f"Degraded: {s['thinking_degraded']}, "
              f"Neutral: {s['thinking_neutral']}")

    print(f"\n  Per-Category:")
    for cat, data in sorted(report.per_category.items()):
        bar = "#" * int(data["avg_quality"] * 20)
        print(f"    {cat:<22} q={data['avg_quality']:.2f} [{bar:<20}] "
              f"{data['avg_latency_ms']:5d}ms  fail={data['failures']}")


def generate_markdown_summary(reports: list[dict]) -> str:
    """Generate a markdown comparison table from multiple report JSONs."""
    lines = [
        "\n## Qwen 3.5 Model Benchmark Results",
        "",
        f"*Tested {datetime.now().strftime('%Y-%m-%d')} on AMD RX 9060 XT 16GB (Vulkan/RADV), "
        f"Ollama 0.18.2*",
        "",
        "### Overall Comparison",
        "",
        "| Model | Avg Quality | >= 0.7 | >= 0.5 | < 0.3 | Gen t/s | Prompt t/s | Avg Latency | P95 | GPU Idle |",
        "|-------|------------|--------|--------|-------|---------|-----------|-------------|-----|----------|",
    ]

    for r in sorted(reports, key=lambda x: x["summary"]["avg_quality"]):
        s = r["summary"]
        lines.append(
            f"| {s['model']} | {s['avg_quality']:.3f} | "
            f"{s['quality_above_0.7']}/{s['total_prompts']} | "
            f"{s['quality_above_0.5']}/{s['total_prompts']} | "
            f"{s['quality_below_0.3']}/{s['total_prompts']} | "
            f"{s['avg_gen_tok_s']} | {s['avg_prompt_tok_s']} | "
            f"{s['avg_latency_ms']}ms | {s['p95_latency_ms']}ms | "
            f"{s['gpu_idle_avg']}% |"
        )

    # Per-category heatmap
    all_cats = sorted(set(
        cat for r in reports for cat in r.get("per_category", {})
    ))
    if all_cats:
        lines.extend([
            "",
            "### Per-Category Quality Scores",
            "",
            "| Category | " + " | ".join(r["summary"]["model"] for r in reports) + " |",
            "|----------|" + "|".join("---" for _ in reports) + "|",
        ])
        for cat in all_cats:
            scores = []
            for r in reports:
                q = r.get("per_category", {}).get(cat, {}).get("avg_quality", 0)
                scores.append(f"{q:.2f}")
            lines.append(f"| {cat} | " + " | ".join(scores) + " |")

    # Thinking mode
    thinking_reports = [r for r in reports if r.get("thinking_results")]
    if thinking_reports:
        lines.extend([
            "",
            "### Thinking Mode Impact",
            "",
            "| Model | Avg Delta | Improved | Degraded | Neutral |",
            "|-------|----------|----------|----------|---------|",
        ])
        for r in thinking_reports:
            s = r["summary"]
            lines.append(
                f"| {s['model']} | {s.get('thinking_avg_delta', 0):+.3f} | "
                f"{s.get('thinking_improved', 0)} | "
                f"{s.get('thinking_degraded', 0)} | "
                f"{s.get('thinking_neutral', 0)} |"
            )

    # Capability boundaries
    lines.extend([
        "",
        "### Capability Boundaries (smallest model with avg quality >= 0.5 per category)",
        "",
    ])
    sorted_reports = sorted(reports, key=lambda x: x["summary"]["avg_quality"])
    for cat in all_cats:
        for r in sorted_reports:
            q = r.get("per_category", {}).get(cat, {}).get("avg_quality", 0)
            if q >= 0.5:
                lines.append(f"- **{cat}**: {r['summary']['model']} (q={q:.2f})")
                break
        else:
            lines.append(f"- **{cat}**: None (all models below 0.5)")

    lines.append("")
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Qwen 3.5 Model Benchmark")
    parser.add_argument("--model", help="Single model to benchmark (e.g. qwen3.5:4b)")
    parser.add_argument("--all", action="store_true", help="Benchmark all qwen3.5 models")
    parser.add_argument("--test-thinking", action="store_true",
                        help="Run thinking mode comparison (20 extra prompts per model)")
    parser.add_argument("--prompts", help="Path to prompts JSON")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Output directory")
    parser.add_argument("--num-predict", type=int, default=2048,
                        help="Max output tokens per response (default: 2048)")
    parser.add_argument("--num-ctx", type=int, default=8192,
                        help="Context window size (default: 8192)")
    parser.add_argument("--summarize", action="store_true",
                        help="Generate markdown summary from existing results")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Summarize existing results
    if args.summarize:
        reports = []
        for f in sorted(output_dir.glob("qwen35-*.json")):
            with open(f) as fh:
                reports.append(json.load(fh))
        if not reports:
            print(f"No reports found in {output_dir}")
            return
        md = generate_markdown_summary(reports)
        print(md)
        # Write to file
        md_path = output_dir / "summary.md"
        md_path.write_text(md)
        print(f"\nSummary written to {md_path}")
        return

    # Determine which models to test
    if args.all:
        models = MODELS
    elif args.model:
        models = [args.model]
    else:
        parser.print_help()
        return

    prompts = load_prompts(args.prompts)

    for i, model in enumerate(models):
        # Unload any previous model
        if i > 0:
            print(f"\n  Unloading previous model...")
            unload_model(models[i - 1])
            time.sleep(5)

        report = benchmark_model(model, prompts,
                                 test_thinking=args.test_thinking,
                                 verbose=args.verbose,
                                 num_predict=args.num_predict,
                                 num_ctx=args.num_ctx)
        print_summary(report)

        # Save report
        size = model.split(":")[-1] if ":" in model else model
        output_path = output_dir / f"qwen35-{size}.json"
        with open(output_path, "w") as f:
            json.dump(asdict(report), f, indent=2)
        print(f"\n  Report saved: {output_path}")

        # Unload after last model
        if i == len(models) - 1:
            unload_model(model)

    # Auto-summarize if we ran all models
    if args.all:
        reports = []
        for f in sorted(output_dir.glob("qwen35-*.json")):
            with open(f) as fh:
                reports.append(json.load(fh))
        if reports:
            md = generate_markdown_summary(reports)
            md_path = output_dir / "summary.md"
            md_path.write_text(md)
            print(f"\n{'='*60}")
            print(md)
            print(f"\nFull summary: {md_path}")


if __name__ == "__main__":
    main()
