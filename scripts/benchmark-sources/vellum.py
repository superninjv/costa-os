"""
Benchmark fetcher: Vellum LLM Leaderboard
URL: https://www.vellum.ai/llm-leaderboard

Extraction strategy (in order):
  1. Check local cache.
  2. Fetch HTML; extract JSON-LD structured data (<script type="application/ld+json">).
     The page embeds Schema.org Dataset nodes, each with a distribution list of
     DataDownload items.  Each item's description encodes the score as:
       "<Model Name> scored X% on <Benchmark>"
     This is the primary and most reliable extraction path.
  3. Fallback: try __NEXT_DATA__ / self.__next_f.push() extraction.
  4. Fallback: HTML table regex.

Known benchmarks: GPQA Diamond, AIME 2025, SWE-Bench Verified,
                  Humanity's Last Exam, ARC-AGI 2, MMMLU

Run standalone:
    python3 scripts/benchmark-sources/vellum.py
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

SOURCE = "vellum"
URL = "https://www.vellum.ai/llm-leaderboard"
BASE_URL = "https://www.vellum.ai"
TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Known benchmark column name patterns (case-insensitive substring match)
BENCHMARK_PATTERNS = [
    ("GPQA Diamond", ["gpqa"]),
    ("AIME 2025", ["aime"]),
    ("SWE-Bench Verified", ["swe"]),
    ("Humanity's Last Exam", ["humanity", "hle"]),
    ("ARC-AGI 2", ["arc-agi", "arcagi"]),
    ("MMMLU", ["mmmlu"]),
    ("MMLU", ["mmlu"]),
]

EMPTY_DF = pd.DataFrame(columns=["model", "benchmark", "score", "source"])


def _fetch_html() -> str | None:
    cached = load_cache(SOURCE)
    if cached:
        return cached
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        html = resp.text
        save_cache(SOURCE, html, ext="html")
        return html
    except requests.RequestException as exc:
        print(f"[{SOURCE}] Fetch error for main URL: {exc}", file=sys.stderr)
        return None


def _to_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, str):
        val = val.replace("%", "").replace(",", "").strip()
        if val in ("", "-", "N/A", "n/a"):
            return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _match_benchmark(text: str) -> str | None:
    text_lower = text.lower()
    for bench_name, patterns in BENCHMARK_PATTERNS:
        if any(p in text_lower for p in patterns):
            return bench_name
    return None


def _extract_from_jsonld(html: str) -> list[dict]:
    """
    Extract benchmark scores from JSON-LD structured data.

    Vellum embeds Schema.org markup in a single <script type="application/ld+json">
    block.  The @graph contains Dataset nodes.  Each Dataset has a distribution
    list of DataDownload items whose description strings encode scores:
        "<Model Name> scored X% on <Benchmark Name>"

    Example:
        {
          "@type": "DataDownload",
          "name": "Claude 3 Opus",
          "description": "Claude 3 Opus scored 95.4% on GPQA Diamond"
        }
    """
    records = []

    jsonld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    for block in jsonld_blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        # The top-level object may be a dict with @graph or a list
        graph_nodes = []
        if isinstance(data, dict) and "@graph" in data:
            graph_nodes = data["@graph"]
        elif isinstance(data, list):
            graph_nodes = data
        elif isinstance(data, dict):
            graph_nodes = [data]

        for node in graph_nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") != "Dataset":
                continue

            distribution = node.get("distribution", [])
            if not isinstance(distribution, list):
                continue

            # Determine benchmark name from the dataset name or variableMeasured
            dataset_name = node.get("variableMeasured") or node.get("name", "")
            benchmark = _match_benchmark(dataset_name)

            for item in distribution:
                if not isinstance(item, dict):
                    continue
                model_name = item.get("name", "").strip()
                description = item.get("description", "")

                if not model_name or not description:
                    continue

                # Parse "Model scored X% on Benchmark" pattern
                score_match = re.search(r"scored\s+([\d.]+)\s*%", description, re.IGNORECASE)
                if not score_match:
                    # Try plain number pattern: "scored X on ..."
                    score_match = re.search(r"scored\s+([\d.]+)\s+on", description, re.IGNORECASE)

                if not score_match:
                    continue

                score = _to_float(score_match.group(1))
                if score is None:
                    continue

                # Use the benchmark from the dataset node, or infer from description
                bench = benchmark
                if bench is None:
                    # Try to infer from description "on <Benchmark>"
                    on_match = re.search(r"\bon\s+(.+)$", description, re.IGNORECASE)
                    if on_match:
                        bench = _match_benchmark(on_match.group(1))

                if bench is None:
                    continue

                records.append({
                    "model": model_name,
                    "benchmark": bench,
                    "score": score,
                    "source": SOURCE,
                })

    return records


def _try_api_endpoints() -> dict | list | None:
    """Try common API patterns and return parsed JSON if found."""
    endpoints = [
        f"{BASE_URL}/api/leaderboard",
        f"{BASE_URL}/api/models",
        f"{BASE_URL}/api/llm-leaderboard",
        f"{BASE_URL}/api/benchmarks",
    ]
    api_headers = {**HEADERS, "Accept": "application/json"}
    for ep in endpoints:
        try:
            resp = requests.get(ep, headers=api_headers, timeout=TIMEOUT)
            if resp.ok and "json" in resp.headers.get("content-type", ""):
                return resp.json()
        except requests.RequestException:
            pass
    return None


def _extract_from_api(data) -> list[dict]:
    """Parse leaderboard data returned from an API endpoint."""
    if isinstance(data, dict):
        for key in ("data", "models", "leaderboard", "results", "rows"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]

    records = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model") or item.get("model_name")
        if not name:
            continue
        for key, val in item.items():
            bench = _match_benchmark(key)
            if bench is None:
                continue
            score = _to_float(val)
            if score is None:
                continue
            records.append({
                "model": str(name),
                "benchmark": bench,
                "score": score,
                "source": SOURCE,
                "cost_input": _to_float(item.get("input_price") or item.get("cost_input")),
                "cost_output": _to_float(item.get("output_price") or item.get("cost_output")),
                "speed_tps": _to_float(item.get("speed") or item.get("tokens_per_second")),
                "context_window": _try_int(item.get("context_window") or item.get("context")),
            })
    return records


def _extract_from_payload(flat_items: list[dict]) -> list[dict]:
    """Walk flattened Next.js payload looking for leaderboard row objects."""
    NAME_KEYS = {"name", "model", "model_name", "modelName", "provider", "llm"}
    SCORE_KEYS = {"gpqa", "aime", "swe", "humanity", "hle", "arc", "mmlu", "score", "rank"}

    records = []
    for item in flat_items:
        if not isinstance(item, dict):
            continue
        name_key = next((k for k in NAME_KEYS if k in item and isinstance(item[k], str)), None)
        if not name_key:
            continue
        has_score = any(
            any(pat in k.lower() for pat in SCORE_KEYS)
            for k in item
        )
        if not has_score:
            continue

        model_name = item[name_key]
        for key, val in item.items():
            bench = _match_benchmark(key)
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
    return records


def _extract_html_table(html: str) -> list[dict]:
    """Regex-based HTML table extraction."""
    records = []

    for table_html in re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE):
        thead = re.search(r"<thead[^>]*>(.*?)</thead>", table_html, re.DOTALL | re.IGNORECASE)
        if not thead:
            continue
        header_cells = re.findall(
            r"<t[hd][^>]*>(.*?)</t[hd]>", thead.group(1), re.DOTALL | re.IGNORECASE
        )
        headers = [re.sub(r"<[^>]+>", "", h).strip() for h in header_cells]
        if not headers:
            continue

        tbody = re.search(r"<tbody[^>]*>(.*?)</tbody>", table_html, re.DOTALL | re.IGNORECASE)
        tbody_html = tbody.group(1) if tbody else table_html

        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_html, re.DOTALL | re.IGNORECASE):
            cells = re.findall(
                r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.DOTALL | re.IGNORECASE
            )
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if len(cells) < 2:
                continue

            model_name = cells[0] if cells else None
            if not model_name or len(model_name) > 80:
                continue

            for i, header in enumerate(headers):
                if i >= len(cells) or i == 0:
                    continue
                bench = _match_benchmark(header)
                if not bench:
                    continue
                score = _to_float(cells[i])
                if score is None:
                    continue
                records.append({
                    "model": model_name,
                    "benchmark": bench,
                    "score": score,
                    "source": SOURCE,
                })

    return records


def _try_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def fetch() -> pd.DataFrame:
    html = _fetch_html()

    records = []

    # Strategy 1: JSON-LD structured data (primary — most reliable for Vellum)
    if html:
        records = _extract_from_jsonld(html)

    # Strategy 2: Next.js embedded data
    if not records and html:
        payloads = extract_nextjs_data(html)
        flat = flatten_nextjs_data(payloads)
        records = _extract_from_payload(flat)

    # Strategy 3: API endpoints
    if not records:
        api_data = _try_api_endpoints()
        if api_data:
            records = _extract_from_api(api_data)

    # Strategy 4: HTML table parsing
    if not records and html:
        records = _extract_html_table(html)

    if not records:
        print(f"[{SOURCE}] No model data found via any extraction strategy.", file=sys.stderr)
        return EMPTY_DF

    df = pd.DataFrame(records)
    for col in ["cost_input", "cost_output", "speed_tps", "context_window"]:
        if col not in df.columns:
            df[col] = None

    print(f"[{SOURCE}] Extracted {len(df)} benchmark score rows.", file=sys.stderr)
    return df


if __name__ == "__main__":
    df = fetch()
    if df.empty:
        print("No data returned.")
    else:
        print(df.to_string(index=False))
