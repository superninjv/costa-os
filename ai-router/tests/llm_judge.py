#!/usr/bin/env python3
"""LLM-as-Judge scoring — replaces keyword matching with Claude-graded quality.

Uses Claude Haiku (via claude CLI) to evaluate model responses on a 5-point
rubric. Much more discriminating than keyword matching: catches factual errors,
reasoning depth, instruction following, and code correctness.

Usage:
    # Score a single response
    python3 llm_judge.py score "what GPU do I have" "You have an AMD RX 9060 XT"

    # Re-score an existing benchmark JSON file
    python3 llm_judge.py rescore ~/Downloads/qwen35-bench/qwen35-9b.json

    # Re-score all benchmarks and regenerate summary
    python3 llm_judge.py rescore-all
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

OUTPUT_DIR = Path.home() / "Downloads" / "qwen35-bench"

JUDGE_SYSTEM_PROMPT = """You are a benchmark quality judge. Score the AI assistant's response to the user's question.

Rate on a 1-5 scale:
5 = Perfect: Accurate, complete, well-structured, directly addresses the question
4 = Good: Mostly accurate with minor omissions or verbosity
3 = Adequate: Partially correct, missing key details, or somewhat off-topic
2 = Poor: Significant errors, mostly irrelevant, or very incomplete
1 = Failure: Wrong answer, refusal when answer is possible, empty, or incoherent

Category-specific criteria:
- system_info/package_query: Without live system data, a GOOD response explains HOW to check (specific commands). A POOR response guesses or says "I don't know" without suggesting commands.
- code_write/code_debug/code_refactor: Code must be syntactically valid and logically correct. Partial solutions that show the right approach score 3-4.
- architecture/deep_knowledge: Evaluate reasoning depth, not just keyword presence. A surface-level answer with the right keywords scores 3. A detailed explanation scores 5.
- code_test: Test cases must be relevant and cover meaningful scenarios.
- web_*: Model should acknowledge it cannot access live data (score 3) rather than hallucinate (score 1-2).

Respond with ONLY a JSON object: {"score": N, "reason": "brief explanation"}"""


def judge_response(prompt: str, response: str, category: str = "",
                   timeout: int = 30) -> tuple[float, str]:
    """Use Claude Haiku to score a response. Returns (score_0_to_1, reason)."""
    if not response or not response.strip():
        return 0.0, "Empty response"

    judge_prompt = f"""Category: {category}
User question: {prompt}
Assistant response: {response[:1500]}

Score this response (1-5):"""

    # Use claude CLI (subscription-based, no API key needed)
    import re

    claude_bin = None
    for path in ["/usr/local/bin/claude", "/usr/bin/claude"]:
        if os.path.exists(path):
            claude_bin = path
            break
    if not claude_bin:
        nvm_dir = os.path.expanduser("~/.nvm/versions/node")
        try:
            versions = sorted(os.listdir(nvm_dir))
            if versions:
                candidate = os.path.join(nvm_dir, versions[-1], "bin", "claude")
                if os.path.exists(candidate):
                    claude_bin = candidate
        except Exception:
            pass

    if not claude_bin:
        return _fallback_score(response, category), "claude CLI not found"

    try:
        result = subprocess.run(
            [claude_bin, "-p",
             "--model", "haiku",
             "--output-format", "text",
             "--system-prompt", JUDGE_SYSTEM_PROMPT],
            input=judge_prompt,
            capture_output=True, text=True,
            timeout=timeout,
            cwd="/tmp",
        )
        output = result.stdout.strip()

        if not output:
            return _fallback_score(response, category), "claude returned empty"

        # Extract JSON from response — Claude may wrap in markdown or add prose
        # Try: bare JSON first
        try:
            parsed = json.loads(output)
            score_raw = parsed.get("score", 3)
            reason = parsed.get("reason", "")
            score = max(0.0, min(1.0, (score_raw - 1) / 4))
            return round(score, 3), reason
        except json.JSONDecodeError:
            pass

        # Try: extract from markdown code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
        if m:
            parsed = json.loads(m.group(1))
            score_raw = parsed.get("score", 3)
            reason = parsed.get("reason", "")
            score = max(0.0, min(1.0, (score_raw - 1) / 4))
            return round(score, 3), reason

        # Try: find any {"score": N, ...} pattern
        m = re.search(r'\{\s*"score"\s*:\s*(\d)', output)
        if m:
            score_raw = int(m.group(1))
            # Try to get reason too
            rm = re.search(r'"reason"\s*:\s*"([^"]*)"', output)
            reason = rm.group(1) if rm else ""
            score = max(0.0, min(1.0, (score_raw - 1) / 4))
            return round(score, 3), reason

        # Last resort: look for just a number 1-5
        m = re.search(r'\b([1-5])\b', output[:20])
        if m:
            score_raw = int(m.group(1))
            score = max(0.0, min(1.0, (score_raw - 1) / 4))
            return round(score, 3), output[:80]

        return _fallback_score(response, category), f"unparseable: {output[:60]}"

    except subprocess.TimeoutExpired:
        return _fallback_score(response, category), "claude timeout"
    except Exception as e:
        return _fallback_score(response, category), f"judge error: {e}"


def _fallback_score(response: str, category: str) -> float:
    """Simple heuristic fallback if Claude is unavailable."""
    if not response or len(response.strip()) < 20:
        return 0.0
    length = len(response)
    # Longer, more detailed responses tend to be better
    if length > 500:
        return 0.65
    elif length > 200:
        return 0.55
    return 0.4


def rescore_benchmark(json_path: str, batch_delay: float = 0.5) -> dict:
    """Re-score all responses in a benchmark JSON using LLM judge.

    Adds 'judge_score' and 'judge_reason' to each result, and updates
    the summary with judge-based quality metrics.
    """
    with open(json_path) as f:
        report = json.load(f)

    results = report.get("results", [])
    model = report.get("model", "unknown")
    print(f"\nRe-scoring {len(results)} responses for {model}...")

    judge_scores = []
    for i, r in enumerate(results, 1):
        prompt = r.get("prompt", "")
        response = r.get("response", "")
        category = r.get("category", "")

        score, reason = judge_response(prompt, response, category)
        r["judge_score"] = score
        r["judge_reason"] = reason
        judge_scores.append(score)

        marker = "." if score >= 0.5 else "X"
        print(f"  [{i:3d}/{len(results)}] kw={r.get('quality_score', 0):.2f} "
              f"judge={score:.2f} {'↑' if score > r.get('quality_score', 0) else '↓'} "
              f"{prompt[:40]}", end="")
        if score < 0.25:
            print(f"  [{reason[:50]}]")
        else:
            print()

        time.sleep(batch_delay)

    # Update summary with judge scores
    summary = report.get("summary", {})
    summary["judge_avg_quality"] = round(mean(judge_scores), 3)
    summary["judge_median_quality"] = round(sorted(judge_scores)[len(judge_scores) // 2], 3)
    summary["judge_above_0.7"] = sum(1 for s in judge_scores if s >= 0.7)
    summary["judge_above_0.5"] = sum(1 for s in judge_scores if s >= 0.5)
    summary["judge_below_0.3"] = sum(1 for s in judge_scores if s < 0.3)
    report["summary"] = summary

    # Update per-category with judge scores
    categories = set(r.get("category", "") for r in results)
    for cat in categories:
        cat_results = [r for r in results if r.get("category") == cat]
        cat_judge = [r.get("judge_score", 0) for r in cat_results]
        if cat in report.get("per_category", {}):
            report["per_category"][cat]["judge_avg_quality"] = round(mean(cat_judge), 3)
            report["per_category"][cat]["judge_min_quality"] = round(min(cat_judge), 3)

    # Save updated report
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  Keyword avg: {summary.get('avg_quality', 0):.3f}")
    print(f"  Judge avg:   {summary['judge_avg_quality']:.3f}")
    print(f"  Judge >= 0.7: {summary['judge_above_0.7']}/{len(results)}")
    print(f"  Judge < 0.3:  {summary['judge_below_0.3']}/{len(results)}")
    print(f"  Saved: {json_path}")

    return report


def rescore_all():
    """Re-score all benchmark JSONs and regenerate the summary."""
    reports = []
    for f in sorted(OUTPUT_DIR.glob("qwen35-*.json")):
        if f.name == "summary.md":
            continue
        report = rescore_benchmark(str(f))
        reports.append(report)

    if reports:
        _generate_judge_summary(reports)


def _generate_judge_summary(reports: list[dict]):
    """Generate a comparison summary using judge scores."""
    lines = [
        "\n## Qwen 3.5 Model Benchmark Results (LLM-Judge Scored)",
        "",
        f"*Re-scored {__import__('datetime').datetime.now().strftime('%Y-%m-%d')} "
        f"using Claude Haiku as quality judge*",
        "",
        "### Overall Comparison",
        "",
        "| Model | Keyword Avg | Judge Avg | Judge ≥0.7 | Judge <0.3 | Gen t/s | Avg Latency |",
        "|-------|------------|-----------|-----------|-----------|---------|-------------|",
    ]

    for r in sorted(reports, key=lambda x: x["summary"].get("judge_avg_quality", 0), reverse=True):
        s = r["summary"]
        lines.append(
            f"| {s['model']} | {s.get('avg_quality', 0):.3f} | "
            f"{s.get('judge_avg_quality', 0):.3f} | "
            f"{s.get('judge_above_0.7', 0)}/{s['total_prompts']} | "
            f"{s.get('judge_below_0.3', 0)}/{s['total_prompts']} | "
            f"{s['avg_gen_tok_s']} | {s['avg_latency_ms']}ms |"
        )

    # Per-category with judge scores
    all_cats = sorted(set(
        cat for r in reports for cat in r.get("per_category", {})
    ))
    if all_cats:
        lines.extend(["", "### Per-Category Quality (Judge Scored)", ""])
        header = "| Category | " + " | ".join(r["summary"]["model"] for r in reports) + " |"
        sep = "|----------|" + "|".join("---" for _ in reports) + "|"
        lines.extend([header, sep])
        for cat in all_cats:
            scores = []
            for r in reports:
                q = r.get("per_category", {}).get(cat, {}).get("judge_avg_quality", 0)
                scores.append(f"{q:.2f}")
            lines.append(f"| {cat} | " + " | ".join(scores) + " |")

    lines.append("")
    md = "\n".join(lines)

    md_path = OUTPUT_DIR / "summary-judge.md"
    md_path.write_text(md)
    print(f"\nJudge summary: {md_path}")
    print(md)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "score" and len(sys.argv) >= 4:
        prompt = sys.argv[2]
        response = sys.argv[3]
        category = sys.argv[4] if len(sys.argv) > 4 else ""
        score, reason = judge_response(prompt, response, category)
        print(f"Score: {score:.3f} ({score * 4 + 1:.0f}/5)")
        print(f"Reason: {reason}")

    elif cmd == "rescore" and len(sys.argv) >= 3:
        rescore_benchmark(sys.argv[2])

    elif cmd == "rescore-all":
        rescore_all()

    else:
        print(__doc__)
