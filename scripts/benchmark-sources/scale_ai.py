"""
Benchmark fetcher: Scale AI SEAL Leaderboard
URL: https://labs.scale.com/leaderboard

Extraction strategy:
  1. Check local cache.
  2. Fetch HTML; extract via __NEXT_DATA__ / self.__next_f.push().
  3. Walk payload for model score objects.
  4. Fall back to searching for JSON arrays in <script> tags.

Benchmark categories present on this site:
  - Agentic: SWE Atlas, MCP Atlas, SWE-Bench Pro
  - Frontier: Humanity's Last Exam, GPQA Diamond
  - Safety benchmarks

Run standalone:
    python3 scripts/benchmark-sources/scale_ai.py
"""

import sys
import json
import re
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _nextjs import extract_nextjs_data, flatten_nextjs_data
from _cache import load_cache, save_cache

SOURCE = "scale_ai"
URL = "https://scale.com/leaderboard"
ALT_URL = "https://labs.scale.com/leaderboard"
TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Benchmark name normalisation: map substrings found in keys/values to
# canonical display names.
BENCHMARK_MAP = [
    ("swe atlas", "SWE Atlas"),
    ("mcp atlas", "MCP Atlas"),
    ("swe-bench pro", "SWE-Bench Pro"),
    ("swebench", "SWE-Bench Pro"),
    ("swe_bench", "SWE-Bench Pro"),
    ("humanity", "Humanity's Last Exam"),
    ("hle", "Humanity's Last Exam"),
    ("gpqa", "GPQA Diamond"),
    ("safety", "Safety"),
    ("agentic", "Agentic Score"),
    ("frontier", "Frontier Score"),
    ("coding", "Coding"),
    ("math", "Math"),
    ("reasoning", "Reasoning"),
    ("instruction", "Instruction Following"),
]

EMPTY_DF = pd.DataFrame(columns=["model", "benchmark", "score", "source"])


def _fetch_html() -> str | None:
    cached = load_cache(SOURCE)
    if cached:
        return cached

    for url in (URL, ALT_URL):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            save_cache(SOURCE, html, ext="html")
            return html
        except requests.RequestException as exc:
            print(f"[{SOURCE}] Fetch error ({url}): {exc}", file=sys.stderr)

    return None


def _to_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, str):
        val = val.replace("%", "").replace(",", "").strip()
        if val in ("", "-", "N/A", "n/a", "TBD"):
            return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _normalise_benchmark(text: str) -> str | None:
    text_lower = text.lower()
    for pattern, name in BENCHMARK_MAP:
        if pattern in text_lower:
            return name
    return None


def _extract_model_rows(flat_items: list[dict]) -> list[dict]:
    """
    Look for dicts that represent leaderboard rows.
    Scale AI's leaderboard may use various key names.
    """
    NAME_KEYS = {"name", "model", "model_name", "modelName", "provider", "llm", "system"}
    records = []

    for item in flat_items:
        if not isinstance(item, dict) or len(item) < 2:
            continue

        name_key = next(
            (k for k in NAME_KEYS if k in item and isinstance(item[k], str) and item[k].strip()),
            None,
        )
        if not name_key:
            continue

        model_name = item[name_key].strip()
        if not model_name or len(model_name) > 100:
            continue

        # Look for score-bearing keys
        for key, val in item.items():
            if key == name_key:
                continue
            bench = _normalise_benchmark(key)
            if bench is None:
                continue
            score = _to_float(val)
            if score is None:
                continue
            records.append({
                "model": model_name,
                "benchmark": bench,
                "score": score,
                "source": SOURCE,
            })

        # Also check for a generic "score" or "rank" at the top level
        for generic_key in ("score", "total_score", "overall", "rank", "rating"):
            if generic_key in item:
                score = _to_float(item[generic_key])
                if score is not None:
                    records.append({
                        "model": model_name,
                        "benchmark": "Scale AI Leaderboard Score",
                        "score": score,
                        "source": SOURCE,
                    })
                    break  # only one generic score per row

    return records


def _scan_script_tags(html: str) -> list[dict]:
    """
    Fallback: scan all <script> blocks for embedded JSON arrays/objects
    containing model data.
    """
    records = []
    for script_body in re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE):
        # Try to find JSON arrays of objects
        for arr_match in re.finditer(r"\[(\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*)\]", script_body, re.DOTALL):
            try:
                arr = json.loads("[" + arr_match.group(1) + "]")
                if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                    flat = []
                    stack = list(arr)
                    while stack:
                        item = stack.pop()
                        if isinstance(item, dict):
                            flat.append(item)
                            stack.extend(item.values())
                        elif isinstance(item, list):
                            stack.extend(item)
                    records.extend(_extract_model_rows(flat))
            except json.JSONDecodeError:
                pass
    return records


def fetch() -> pd.DataFrame:
    html = _fetch_html()
    if not html:
        return EMPTY_DF

    # Primary: Next.js extraction
    payloads = extract_nextjs_data(html)
    flat = flatten_nextjs_data(payloads)
    records = _extract_model_rows(flat)

    # Fallback: scan <script> tags
    if not records:
        records = _scan_script_tags(html)

    if not records:
        print(f"[{SOURCE}] No model data found in page payload.", file=sys.stderr)
        return EMPTY_DF

    df = pd.DataFrame(records)
    # Deduplicate
    df = df.drop_duplicates(subset=["model", "benchmark"])

    print(f"[{SOURCE}] Extracted {len(df)} benchmark score rows.", file=sys.stderr)
    return df


if __name__ == "__main__":
    df = fetch()
    if df.empty:
        print("No data returned.")
    else:
        print(df.to_string(index=False))
