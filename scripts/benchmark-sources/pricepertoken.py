"""
Benchmark fetcher: pricepertoken.com
URL: https://pricepertoken.com

Primary data type: pricing (cost_input, cost_output per M tokens), context window.
Secondary data: some benchmark scores may be present.

Extraction strategy:
  1. Check local cache.
  2. Fetch main HTML page; try __NEXT_DATA__ extraction.
  3. Try API endpoints: /api/models, /api/pricing.
  4. Scan <script> tags for embedded JSON.
  5. Regex-parse any visible pricing tables in HTML.

Output schema follows the standard DataFrame contract.  Where no benchmark
score is available a synthetic "Pricing Data" row is emitted with score=NaN
so that cost/context metadata is still captured.

Run standalone:
    python3 scripts/benchmark-sources/pricepertoken.py
"""

import sys
import json
import re
import math
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _nextjs import extract_nextjs_data, flatten_nextjs_data
from _cache import load_cache, save_cache

SOURCE = "pricepertoken"
URL = "https://pricepertoken.com"
TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

EMPTY_DF = pd.DataFrame(columns=["model", "benchmark", "score", "source"])

# Heuristic key groups for pricing data
NAME_KEYS = {"name", "model", "model_name", "modelName", "id", "slug", "title"}
PRICE_IN_KEYS = {
    "input_price", "price_input", "cost_input", "inputPrice", "input_cost",
    "pricePerInputToken", "input", "prompt_price", "promptPrice",
    "price_per_input_token", "input_token_price",
}
PRICE_OUT_KEYS = {
    "output_price", "price_output", "cost_output", "outputPrice", "output_cost",
    "pricePerOutputToken", "output", "completion_price", "completionPrice",
    "price_per_output_token", "output_token_price",
}
CTX_KEYS = {
    "context_window", "context", "contextWindow", "context_length",
    "contextLength", "max_tokens", "maxTokens", "max_context",
}
PROVIDER_KEYS = {"provider", "company", "vendor", "org", "organization"}

# Known benchmark keys that pricepertoken might include
BENCH_MAP = [
    ("mmlu", "MMLU"),
    ("gpqa", "GPQA Diamond"),
    ("hellaswag", "HellaSwag"),
    ("arc", "ARC"),
    ("truthful", "TruthfulQA"),
    ("humaneval", "HumanEval"),
    ("mbpp", "MBPP"),
    ("gsm8k", "GSM8K"),
    ("math", "MATH"),
]


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
        print(f"[{SOURCE}] Fetch error: {exc}", file=sys.stderr)
        return None


def _try_api(base_url: str) -> list | dict | None:
    endpoints = [
        f"{base_url}/api/models",
        f"{base_url}/api/pricing",
        f"{base_url}/api/data",
        f"{base_url}/data/models.json",
        f"{base_url}/models.json",
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


def _to_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, str):
        # Remove common formatting: $, commas, spaces, trailing 'M'
        val = val.replace("$", "").replace(",", "").strip()
        if val in ("", "-", "N/A", "n/a"):
            return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _to_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _extract_pricing_rows(flat_items: list[dict]) -> list[dict]:
    rows = []
    for item in flat_items:
        if not isinstance(item, dict):
            continue
        name_key = next((k for k in NAME_KEYS if k in item and isinstance(item[k], str) and item[k].strip()), None)
        if not name_key:
            continue

        price_in_key = next((k for k in PRICE_IN_KEYS if k in item), None)
        price_out_key = next((k for k in PRICE_OUT_KEYS if k in item), None)
        ctx_key = next((k for k in CTX_KEYS if k in item), None)
        prov_key = next((k for k in PROVIDER_KEYS if k in item), None)

        # Must have at least one pricing field to be a relevant row
        if not price_in_key and not price_out_key:
            continue

        model_name = item[name_key].strip()
        row = {
            "model": model_name,
            "cost_input": _to_float(item.get(price_in_key)) if price_in_key else None,
            "cost_output": _to_float(item.get(price_out_key)) if price_out_key else None,
            "context_window": _to_int(item.get(ctx_key)) if ctx_key else None,
            "provider": item.get(prov_key) if prov_key else None,
        }

        # Check for benchmark scores
        bench_records = []
        for key, val in item.items():
            for pattern, bench_name in BENCH_MAP:
                if pattern in key.lower():
                    score = _to_float(val)
                    if score is not None:
                        bench_records.append((bench_name, score))

        if bench_records:
            for bench_name, score in bench_records:
                rows.append({**row, "benchmark": bench_name, "score": score})
        else:
            rows.append({**row, "benchmark": "Pricing Data", "score": float("nan")})

    return rows


def _parse_html_table(html: str) -> list[dict]:
    """
    Regex-based table extraction for pricing tables that may not be in JSON.
    """
    rows = []
    for table_html in re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE):
        thead = re.search(r"<thead[^>]*>(.*?)</thead>", table_html, re.DOTALL | re.IGNORECASE)
        if not thead:
            continue
        header_cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", thead.group(1), re.DOTALL | re.IGNORECASE)
        headers = [re.sub(r"<[^>]+>", "", h).strip().lower() for h in header_cells]
        if not headers:
            continue

        # Map header indices
        model_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ("model", "name"))), None)
        if model_idx is None:
            continue

        in_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ("input", "prompt"))), None)
        out_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ("output", "completion"))), None)
        ctx_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ("context", "tokens", "window"))), None)
        prov_idx = next((i for i, h in enumerate(headers) if any(k in h for k in ("provider", "company", "vendor"))), None)

        tbody = re.search(r"<tbody[^>]*>(.*?)</tbody>", table_html, re.DOTALL | re.IGNORECASE)
        tbody_html = tbody.group(1) if tbody else table_html

        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_html, re.DOTALL | re.IGNORECASE):
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.DOTALL | re.IGNORECASE)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if len(cells) <= model_idx:
                continue

            model_name = cells[model_idx]
            if not model_name or len(model_name) > 100:
                continue

            row = {
                "model": model_name,
                "benchmark": "Pricing Data",
                "score": float("nan"),
                "source": SOURCE,
                "cost_input": _to_float(cells[in_idx]) if in_idx and in_idx < len(cells) else None,
                "cost_output": _to_float(cells[out_idx]) if out_idx and out_idx < len(cells) else None,
                "context_window": _to_int(cells[ctx_idx]) if ctx_idx and ctx_idx < len(cells) else None,
            }
            if any(v is not None for v in [row["cost_input"], row["cost_output"], row["context_window"]]):
                rows.append(row)

    return rows


def fetch() -> pd.DataFrame:
    html = _fetch_html()

    rows = []

    # Strategy 1: Next.js payload extraction
    if html:
        payloads = extract_nextjs_data(html)
        flat = flatten_nextjs_data(payloads)
        rows = _extract_pricing_rows(flat)

    # Strategy 2: Scan <script> tags for JSON
    if not rows and html:
        for script_body in re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE):
            for arr_match in re.finditer(r"\[(\s*\{.*?\}\s*(?:,\s*\{.*?\}\s*)*)\]", script_body, re.DOTALL):
                try:
                    arr = json.loads("[" + arr_match.group(1) + "]")
                    if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                        from _nextjs import flatten_nextjs_data as _flat
                        candidate = _extract_pricing_rows(_flat([arr]))
                        rows.extend(candidate)
                except json.JSONDecodeError:
                    pass

    # Strategy 3: API endpoints
    if not rows:
        api_data = _try_api(URL)
        if api_data:
            if isinstance(api_data, list):
                items = api_data
            elif isinstance(api_data, dict):
                items = api_data.get("data") or api_data.get("models") or list(api_data.values())
            else:
                items = []
            rows = _extract_pricing_rows(items)

    # Strategy 4: HTML table parsing
    if not rows and html:
        rows = _parse_html_table(html)

    if not rows:
        print(f"[{SOURCE}] No pricing/model data found via any extraction strategy.", file=sys.stderr)
        return EMPTY_DF

    df = pd.DataFrame(rows)
    df["source"] = SOURCE

    # Ensure all optional columns exist
    for col in ["cost_input", "cost_output", "context_window", "speed_tps"]:
        if col not in df.columns:
            df[col] = None

    # Drop rows where we have neither pricing nor score
    useful = df.dropna(subset=["cost_input", "cost_output", "context_window", "score"], how="all")
    if useful.empty:
        # Keep all rows if nothing passes the filter (score column is NaN by design)
        useful = df

    print(f"[{SOURCE}] Extracted {len(useful)} rows (pricing + benchmark).", file=sys.stderr)
    return useful


if __name__ == "__main__":
    df = fetch()
    if df.empty:
        print("No data returned.")
    else:
        print(df.to_string(index=False))
