"""
Benchmark fetcher: Artificial Analysis leaderboard
URL: https://artificialanalysis.ai/leaderboards/models

Extraction strategy:
  1. Check local cache (< 12 h old) to avoid unnecessary requests.
  2. Fetch the Next.js page via RSC (React Server Component) streaming endpoint
     using the RSC: 1 header, which returns a text/x-component stream.
  3. Parse RSC lines to find the large models array in the page's server props.
  4. Walk the models list extracting intelligence_index, speed, pricing.
  5. Return a DataFrame with columns: model, benchmark, score, source
     plus optional: cost_input, cost_output, speed_tps, context_window.

Run standalone for a quick smoke test:
    python3 scripts/benchmark-sources/artificial_analysis.py
"""

import sys
import json
import re
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _cache import load_cache, save_cache

SOURCE = "artificial_analysis"
# The /leaderboards/models page URL (the original URL is now 404, but RSC fetch still works)
URL = "https://artificialanalysis.ai/leaderboards/models"
TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/x-component,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    # RSC: 1 tells Next.js to return the React Server Component streaming payload
    # instead of full HTML, giving us structured data directly.
    "RSC": "1",
    "Next-Router-State-Tree": (
        "%5B%22%22%2C%7B%22children%22%3A%5B%22(pages)%22%2C%7B%22children%22%3A"
        "%5B%22leaderboards%22%2C%7B%22children%22%3A%5B%22models%22%2C%7B%22children%22"
        "%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
    ),
}

EMPTY_DF = pd.DataFrame(columns=["model", "benchmark", "score", "source"])


def _fetch_rsc() -> str | None:
    cached = load_cache(SOURCE)
    if cached:
        return cached
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        # RSC responses arrive as text/x-component; status may show 404 for the
        # HTML page but the RSC stream still delivers model data.
        content = resp.text
        if not content or len(content) < 1000:
            print(f"[{SOURCE}] RSC response too short ({len(content)} chars).", file=sys.stderr)
            return None
        save_cache(SOURCE, content, ext="txt")
        return content
    except requests.RequestException as exc:
        print(f"[{SOURCE}] Fetch error: {exc}", file=sys.stderr)
        return None


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _find_models_array_in_rsc(rsc_text: str) -> list[dict]:
    """
    The RSC stream is newline-delimited.  Each line is:
        <hex_id>:<type_prefix><payload>
    The leaderboard data sits in the largest line which contains a React element
    tree prop named 'models' holding the full model array.

    We parse each line that starts with a valid JSON array/object and recursively
    search for a 'models' key whose value is a list of dicts with 'intelligence_index'.
    """
    def find_key(obj, key, depth=0):
        """Recursively find first value for *key* in nested JSON."""
        if depth > 10:
            return None
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                result = find_key(v, key, depth + 1)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = find_key(item, key, depth + 1)
                if result is not None:
                    return result
        return None

    lines = rsc_text.split("\n")
    # Sort lines by length descending — the model data is in the largest line
    sorted_lines = sorted(lines, key=len, reverse=True)

    for line in sorted_lines[:10]:  # Only check the largest lines
        if len(line) < 10000:
            break
        colon_idx = line.find(":")
        if colon_idx < 0:
            continue
        payload = line[colon_idx + 1:]
        if not payload or payload[0] not in "[{":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue

        models = find_key(obj, "models")
        if not isinstance(models, list) or not models:
            continue
        # Validate that this looks like the right array
        if isinstance(models[0], dict) and "intelligence_index" in models[0]:
            return models

    return []


def fetch() -> pd.DataFrame:
    rsc_text = _fetch_rsc()
    if not rsc_text:
        return EMPTY_DF

    models = _find_models_array_in_rsc(rsc_text)
    if not models:
        print(f"[{SOURCE}] No model data found in RSC payload.", file=sys.stderr)
        return EMPTY_DF

    records = []
    for m in models:
        if not isinstance(m, dict):
            continue
        name = m.get("name") or m.get("short_name")
        if not name:
            continue

        intelligence_index = _to_float(m.get("intelligence_index"))
        speed_tps = None

        # Speed is nested inside timescaleData
        timescale = m.get("timescaleData")
        if isinstance(timescale, dict):
            speed_tps = _to_float(timescale.get("median_output_speed"))

        cost_input = _to_float(m.get("price_1m_input_tokens"))
        cost_output = _to_float(m.get("price_1m_output_tokens"))
        context_window = _to_int(m.get("context_window_tokens"))

        if intelligence_index is None and speed_tps is None and cost_input is None:
            continue

        records.append({
            "model": name,
            "benchmark": "Artificial Analysis Intelligence Index",
            "score": intelligence_index if intelligence_index is not None else float("nan"),
            "source": SOURCE,
            "cost_input": cost_input,
            "cost_output": cost_output,
            "speed_tps": speed_tps,
            "context_window": context_window,
        })

    if not records:
        print(f"[{SOURCE}] Parsed models but found no usable rows.", file=sys.stderr)
        return EMPTY_DF

    df = pd.DataFrame(records)
    metric_cols = ["score", "cost_input", "cost_output", "speed_tps", "context_window"]
    existing_metrics = [c for c in metric_cols if c in df.columns]
    df = df.dropna(subset=existing_metrics, how="all")

    print(f"[{SOURCE}] Extracted {len(df)} model rows.", file=sys.stderr)
    return df


if __name__ == "__main__":
    df = fetch()
    if df.empty:
        print("No data returned.")
    else:
        print(df.to_string(index=False))
