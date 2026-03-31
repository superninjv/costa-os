#!/usr/bin/env python3
"""Costa AI Router — 100-Prompt Test Harness.

Runs a set of test prompts through costa-ai, scores routing accuracy,
response quality, and latency. Outputs a JSON report for benchmarking
and model comparison.

Usage:
    # Run full benchmark with current model
    python3 test_harness.py --model-tag qwen2.5-baseline

    # Skip cloud-dependent and window manager prompts (local-only test)
    python3 test_harness.py --model-tag qwen2.5-local --skip-cloud --skip-window-mgr

    # Compare two reports
    python3 test_harness.py --compare report_a.json report_b.json

    # Use custom prompts
    python3 test_harness.py --prompts my_prompts.json --model-tag custom
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

# ─── Types ───────────────────────────────────────────────────

@dataclass
class TestPrompt:
    prompt: str
    expected_route: str
    category: str
    quality_keywords: list[str]
    anti_keywords: list[str]
    max_latency_ms: int
    should_escalate: bool


@dataclass
class TestResult:
    prompt: str
    expected_route: str
    actual_route: str
    route_correct: bool
    category: str
    quality_score: float
    latency_ms: int
    escalated: bool
    expected_escalation: bool
    latency_ok: bool
    response_preview: str
    model_used: str
    error: str | None = None


# ─── Route matching ──────────────────────────────────────────

# Routes that should be considered equivalent for scoring
ROUTE_ALIASES = {
    "local_will_escalate": {"local_will_escalate", "local"},
    "window_manager": {"window_manager", "local"},
    "meta": {"meta"},
    "local": {"local"},
    "haiku+web": {"haiku+web", "haiku"},
    "sonnet": {"sonnet"},
    "opus": {"opus"},
    "file_search": {"file_search"},
    "local+weather": {"local+weather", "local", "meta"},
}


def route_matches(expected: str, actual: str) -> bool:
    """Check if actual route matches expected, considering aliases."""
    if expected == actual:
        return True
    aliases = ROUTE_ALIASES.get(expected, {expected})
    return actual in aliases


# ─── Quality scoring ─────────────────────────────────────────

def score_quality(response: str, keywords: list[str], anti_keywords: list[str]) -> float:
    """Score response quality 0.0-1.0 based on keyword presence."""
    if not response or not response.strip():
        return 0.0

    resp_lower = response.lower()
    score = 0.5  # baseline: got a non-empty response

    # Positive keywords
    if keywords:
        hits = sum(1 for kw in keywords if kw.lower() in resp_lower)
        score += 0.5 * (hits / len(keywords))

    # Anti-keywords (penalize)
    if anti_keywords:
        anti_hits = sum(1 for kw in anti_keywords if kw.lower() in resp_lower)
        if anti_hits > 0:
            score -= 0.3 * (anti_hits / len(anti_keywords))

    return max(0.0, min(1.0, score))


# ─── Run a single prompt ─────────────────────────────────────

def run_prompt(prompt: TestPrompt, skip_execute: bool = False) -> TestResult:
    """Run a single prompt through costa-ai and score the result."""
    cmd = ["costa-ai", "--json"]

    # Window manager prompts: dry run to avoid touching windows
    if prompt.expected_route == "window_manager" or skip_execute:
        cmd.append("--no-execute")

    # Cloud-dependent prompts still go through the router normally
    # (the router decides whether to escalate)

    cmd.append(prompt.prompt)

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            env={**os.environ, "COSTA_AI_SOURCE": "test_harness"},
        )
        wall_ms = int((time.monotonic() - start) * 1000)
    except subprocess.TimeoutExpired:
        wall_ms = 120000
        return TestResult(
            prompt=prompt.prompt,
            expected_route=prompt.expected_route,
            actual_route="timeout",
            route_correct=False,
            category=prompt.category,
            quality_score=0.0,
            latency_ms=wall_ms,
            escalated=False,
            expected_escalation=prompt.should_escalate,
            latency_ok=False,
            response_preview="",
            model_used="",
            error="Timed out after 120s",
        )

    # Parse JSON output
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return TestResult(
            prompt=prompt.prompt,
            expected_route=prompt.expected_route,
            actual_route="parse_error",
            route_correct=False,
            category=prompt.category,
            quality_score=0.0,
            latency_ms=wall_ms,
            escalated=False,
            expected_escalation=prompt.should_escalate,
            latency_ok=False,
            response_preview=result.stdout[:200] if result.stdout else result.stderr[:200],
            model_used="",
            error=f"Failed to parse JSON: {result.stderr[:200]}",
        )

    response = data.get("response", "")
    actual_route = data.get("route", "unknown")
    model_used = data.get("model", "unknown")
    escalated = data.get("escalated", False)
    latency = data.get("elapsed_ms", wall_ms)

    return TestResult(
        prompt=prompt.prompt,
        expected_route=prompt.expected_route,
        actual_route=actual_route,
        route_correct=route_matches(prompt.expected_route, actual_route),
        category=prompt.category,
        quality_score=round(score_quality(response, prompt.quality_keywords, prompt.anti_keywords), 3),
        latency_ms=latency,
        escalated=escalated,
        expected_escalation=prompt.should_escalate,
        latency_ok=latency <= prompt.max_latency_ms,
        response_preview=response[:200] if response else "",
        model_used=model_used,
    )


# ─── Report generation ───────────────────────────────────────

def generate_report(results: list[TestResult], model_tag: str, local_model: str, duration_s: float) -> dict:
    """Generate a structured report from test results."""
    total = len(results)
    if total == 0:
        return {"error": "No results"}

    route_correct = sum(1 for r in results if r.route_correct)
    quality_scores = [r.quality_score for r in results]
    latencies = [r.latency_ms for r in results]
    escalated = sum(1 for r in results if r.escalated)
    latency_ok = sum(1 for r in results if r.latency_ok)
    errors = [r for r in results if r.error]

    # Per-route accuracy
    routes = set(r.expected_route for r in results)
    per_route = {}
    for route in sorted(routes):
        route_results = [r for r in results if r.expected_route == route]
        correct = sum(1 for r in route_results if r.route_correct)
        per_route[route] = {
            "accuracy": round(correct / len(route_results), 3) if route_results else 0,
            "count": len(route_results),
            "correct": correct,
            "avg_quality": round(mean(r.quality_score for r in route_results), 3),
            "avg_latency_ms": int(mean(r.latency_ms for r in route_results)),
        }

    # Per-category breakdown
    categories = set(r.category for r in results)
    per_category = {}
    for cat in sorted(categories):
        cat_results = [r for r in results if r.category == cat]
        per_category[cat] = {
            "count": len(cat_results),
            "avg_quality": round(mean(r.quality_score for r in cat_results), 3),
            "avg_latency_ms": int(mean(r.latency_ms for r in cat_results)),
        }

    sorted_latencies = sorted(latencies)
    p50_idx = len(sorted_latencies) // 2
    p95_idx = int(len(sorted_latencies) * 0.95)

    return {
        "meta": {
            "model_tag": model_tag,
            "local_model": local_model,
            "timestamp": datetime.now().isoformat(),
            "total_prompts": total,
            "duration_s": round(duration_s, 1),
        },
        "summary": {
            "routing_accuracy": round(route_correct / total, 3),
            "avg_quality_score": round(mean(quality_scores), 3),
            "avg_latency_ms": int(mean(latencies)),
            "median_latency_ms": int(median(latencies)),
            "p50_latency_ms": sorted_latencies[p50_idx] if sorted_latencies else 0,
            "p95_latency_ms": sorted_latencies[p95_idx] if sorted_latencies else 0,
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
            "escalation_rate": round(escalated / total, 3),
            "latency_pass_rate": round(latency_ok / total, 3),
            "error_count": len(errors),
        },
        "per_route": per_route,
        "per_category": per_category,
        "results": [asdict(r) for r in results],
        "failures": [asdict(r) for r in results if not r.route_correct or r.quality_score < 0.3],
    }


# ─── Comparison ───────────────────────────────────────────────

def compare_reports(path_a: str, path_b: str):
    """Compare two benchmark reports side-by-side."""
    with open(path_a) as f:
        a = json.load(f)
    with open(path_b) as f:
        b = json.load(f)

    sa, sb = a["summary"], b["summary"]
    tag_a = a["meta"]["model_tag"]
    tag_b = b["meta"]["model_tag"]

    print(f"\n{'='*60}")
    print(f"  Comparison: {tag_a} vs {tag_b}")
    print(f"{'='*60}\n")

    metrics = [
        ("Routing Accuracy", "routing_accuracy", True),
        ("Avg Quality Score", "avg_quality_score", True),
        ("Avg Latency (ms)", "avg_latency_ms", False),
        ("P95 Latency (ms)", "p95_latency_ms", False),
        ("Escalation Rate", "escalation_rate", None),
        ("Error Count", "error_count", False),
    ]

    print(f"  {'Metric':<25} {tag_a:>12} {tag_b:>12} {'Delta':>10} {'Winner':>8}")
    print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*10} {'-'*8}")

    for label, key, higher_is_better in metrics:
        va, vb = sa[key], sb[key]
        delta = vb - va
        if isinstance(va, float):
            delta_str = f"{delta:+.3f}"
            va_str = f"{va:.3f}"
            vb_str = f"{vb:.3f}"
        else:
            delta_str = f"{delta:+d}"
            va_str = str(va)
            vb_str = str(vb)

        if higher_is_better is None:
            winner = ""
        elif (higher_is_better and delta > 0) or (not higher_is_better and delta < 0):
            winner = tag_b
        elif (higher_is_better and delta < 0) or (not higher_is_better and delta > 0):
            winner = tag_a
        else:
            winner = "tie"

        print(f"  {label:<25} {va_str:>12} {vb_str:>12} {delta_str:>10} {winner:>8}")

    # Per-route comparison
    print(f"\n  Per-Route Accuracy:")
    all_routes = sorted(set(list(a.get("per_route", {}).keys()) + list(b.get("per_route", {}).keys())))
    for route in all_routes:
        ra = a.get("per_route", {}).get(route, {}).get("accuracy", "N/A")
        rb = b.get("per_route", {}).get(route, {}).get("accuracy", "N/A")
        ra_str = f"{ra:.3f}" if isinstance(ra, (int, float)) else ra
        rb_str = f"{rb:.3f}" if isinstance(rb, (int, float)) else rb
        print(f"    {route:<25} {ra_str:>8} -> {rb_str:>8}")

    # Regressions and improvements
    if "results" in a and "results" in b:
        a_by_prompt = {r["prompt"]: r for r in a["results"]}
        b_by_prompt = {r["prompt"]: r for r in b["results"]}

        regressions = []
        improvements = []
        for prompt in a_by_prompt:
            if prompt in b_by_prompt:
                ra = a_by_prompt[prompt]
                rb = b_by_prompt[prompt]
                if ra["route_correct"] and not rb["route_correct"]:
                    regressions.append(prompt)
                elif not ra["route_correct"] and rb["route_correct"]:
                    improvements.append(prompt)

        if improvements:
            print(f"\n  Improvements ({len(improvements)}):")
            for p in improvements[:10]:
                print(f"    + {p[:60]}")

        if regressions:
            print(f"\n  Regressions ({len(regressions)}):")
            for p in regressions[:10]:
                print(f"    - {p[:60]}")

    print()


# ─── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Costa AI Router — 100-Prompt Test Harness")
    parser.add_argument("--model-tag", default="default", help="Label for this test run (e.g. 'qwen2.5-baseline')")
    parser.add_argument("--output", help="Output report path (default: auto-generated)")
    parser.add_argument("--prompts", default=str(Path(__file__).parent / "prompts_100.json"),
                        help="Path to prompts JSON file")
    parser.add_argument("--skip-cloud", action="store_true", help="Skip prompts that require cloud models")
    parser.add_argument("--skip-window-mgr", action="store_true", help="Skip window manager prompts")
    parser.add_argument("--skip-meta", action="store_true", help="Skip meta prompts")
    parser.add_argument("--only-route", help="Only run prompts for a specific route (e.g. 'local')")
    parser.add_argument("--compare", nargs=2, metavar=("REPORT_A", "REPORT_B"),
                        help="Compare two reports instead of running tests")
    parser.add_argument("--force-model", help="Override /tmp/ollama-smart-model for this run (e.g. qwen3.5:4b)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each result as it completes")
    args = parser.parse_args()

    if args.compare:
        compare_reports(args.compare[0], args.compare[1])
        return

    # Override local model if requested
    original_model = None
    xdg = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "costa/ollama-smart-model"
    model_file = xdg if xdg.exists() else Path("/tmp/ollama-smart-model")
    if args.force_model:
        try:
            original_model = model_file.read_text().strip()
        except Exception:
            original_model = None
        model_file.write_text(args.force_model)
        print(f"  Forcing model: {args.force_model}")

    # Load prompts
    with open(args.prompts) as f:
        raw_prompts = json.load(f)

    prompts = [TestPrompt(**p) for p in raw_prompts]

    # Apply filters
    if args.skip_cloud:
        cloud_routes = {"haiku+web", "sonnet", "opus"}
        prompts = [p for p in prompts if p.expected_route not in cloud_routes]
    if args.skip_window_mgr:
        prompts = [p for p in prompts if p.expected_route != "window_manager"]
    if args.skip_meta:
        prompts = [p for p in prompts if p.expected_route != "meta"]
    if args.only_route:
        prompts = [p for p in prompts if p.expected_route == args.only_route]

    if not prompts:
        print("No prompts to test after filtering.")
        return

    # Detect current model
    try:
        local_model = model_file.read_text().strip()
    except Exception:
        local_model = "unknown"

    print(f"Costa AI Router — Test Harness")
    print(f"  Model tag: {args.model_tag}")
    print(f"  Local model: {local_model}")
    print(f"  Prompts: {len(prompts)}")
    print(f"  Filters: {'skip-cloud ' if args.skip_cloud else ''}{'skip-wm ' if args.skip_window_mgr else ''}{'only-' + args.only_route if args.only_route else ''}")
    print()

    # Run all prompts
    results: list[TestResult] = []
    start_time = time.monotonic()

    for i, prompt in enumerate(prompts, 1):
        if args.verbose:
            print(f"  [{i:3d}/{len(prompts)}] {prompt.prompt[:50]}...", end=" ", flush=True)

        result = run_prompt(prompt, skip_execute=(prompt.expected_route == "window_manager"))
        results.append(result)

        if args.verbose:
            status = "OK" if result.route_correct else "MISS"
            print(f"{result.actual_route:<20} q={result.quality_score:.2f} {result.latency_ms:5d}ms [{status}]")
        else:
            # Progress indicator
            marker = "." if result.route_correct else "X"
            print(marker, end="", flush=True)
            if i % 50 == 0:
                print(f" [{i}/{len(prompts)}]")

    duration_s = time.monotonic() - start_time
    if not args.verbose:
        print(f" [{len(prompts)}/{len(prompts)}]")

    # Generate report
    report = generate_report(results, args.model_tag, local_model, duration_s)

    # Write report
    if args.output:
        output_path = args.output
    else:
        output_path = f"test_report_{args.model_tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    s = report["summary"]
    print(f"\n{'='*50}")
    print(f"  RESULTS: {args.model_tag}")
    print(f"{'='*50}")
    print(f"  Routing Accuracy:  {s['routing_accuracy']:.1%}")
    print(f"  Avg Quality:       {s['avg_quality_score']:.3f}")
    print(f"  Avg Latency:       {s['avg_latency_ms']}ms")
    print(f"  P50 Latency:       {s['p50_latency_ms']}ms")
    print(f"  P95 Latency:       {s['p95_latency_ms']}ms")
    print(f"  Escalation Rate:   {s['escalation_rate']:.1%}")
    print(f"  Latency Pass Rate: {s['latency_pass_rate']:.1%}")
    print(f"  Errors:            {s['error_count']}")
    print(f"  Duration:          {duration_s:.1f}s")
    print(f"  Report:            {output_path}")

    # Print per-route summary
    print(f"\n  Per-Route:")
    for route, data in sorted(report["per_route"].items()):
        print(f"    {route:<25} {data['correct']}/{data['count']} ({data['accuracy']:.0%})  q={data['avg_quality']:.2f}  {data['avg_latency_ms']}ms")

    # Print failures
    failures = report.get("failures", [])
    if failures:
        print(f"\n  Failures ({len(failures)}):")
        for f in failures[:15]:
            reason = "misrouted" if not f["route_correct"] else f"low quality ({f['quality_score']:.2f})"
            print(f"    [{reason}] {f['prompt'][:50]}  expected={f['expected_route']} got={f['actual_route']}")
        if len(failures) > 15:
            print(f"    ... and {len(failures) - 15} more (see report)")

    # Restore original model if we overrode it
    if args.force_model and original_model is not None:
        model_file.write_text(original_model)
        print(f"\n  Restored model: {original_model}")

    print()


if __name__ == "__main__":
    main()
