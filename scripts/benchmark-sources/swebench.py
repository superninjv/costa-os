"""
swebench.py — Fetcher for SWE-bench leaderboard data.

SWE-bench measures whether AI systems can autonomously resolve real GitHub
issues from popular Python repositories. The key metric is "resolve rate"
(% of issues fully fixed, verified by running the repo's test suite).

Variants:
  - SWE-bench Verified: human-validated subset, ~500 issues
  - SWE-bench Lite: curated 300-issue subset, commonly used for quick evals
  - SWE-bench Test: full ~2,294 issues
  - SWE-bench Multimodal: vision-enabled variant

Data source: https://www.swebench.com (inline JSON leaderboard-data script tag)
  The website embeds all leaderboard results as a JSON blob in the HTML,
  including model name, resolve percentage, and benchmark category.

Update frequency: continuous (community submissions).
"""

import io
import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from _cache import load_cache, save_cache

SOURCE = "swebench"
SWEBENCH_WEBSITE = "https://www.swebench.com"

# Map category names from the website's JSON -> standardised benchmark labels
CATEGORY_LABEL_MAP = {
    "verified": "SWE-bench Verified",
    "lite": "SWE-bench Lite",
    "test": "SWE-bench Test",
    "multimodal": "SWE-bench Multimodal",
    "multilingual": "SWE-bench Multilingual",
    "bash-only": "SWE-bench Verified (bash-only)",
}


def _get(url: str, timeout: int = 30) -> requests.Response | None:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        print(f"[swebench] HTTP error {url}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[swebench] Error {url}: {exc}", file=sys.stderr)
        return None


def _scrape_website() -> pd.DataFrame:
    """
    Scrape the leaderboard data from swebench.com.

    The website embeds all results as a JSON array in a <script> tag with
    id="leaderboard-data".  Each element is a category dict:
        {
          "name": "Verified",
          "results": [
            {"name": "Claude 4 Sonnet", "resolved": 72.0, "date": "2025-05-22"},
            ...
          ]
        }
    """
    resp = _get(SWEBENCH_WEBSITE, timeout=30)
    if resp is None:
        return pd.DataFrame()

    html = resp.text

    # Extract the inline JSON
    m = re.search(
        r'<script[^>]+id=["\']leaderboard-data["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        print("[swebench] Could not find leaderboard-data script tag.", file=sys.stderr)
        return pd.DataFrame()

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        print(f"[swebench] JSON parse error: {exc}", file=sys.stderr)
        return pd.DataFrame()

    rows = []
    for category in data:
        cat_name = str(category.get("name", "")).strip()
        bench_label = CATEGORY_LABEL_MAP.get(cat_name.lower(), f"SWE-bench {cat_name}")
        results = category.get("results", [])
        for entry in results:
            model_name = str(entry.get("name", "")).strip()
            resolved = entry.get("resolved")
            if not model_name or resolved is None:
                continue
            try:
                score = float(str(resolved).replace("%", "").strip())
            except (ValueError, TypeError):
                continue
            rows.append(
                {
                    "model": model_name,
                    "benchmark": bench_label,
                    "score": score,
                    "source": SOURCE,
                }
            )

    if not rows:
        print("[swebench] No results extracted from website JSON.", file=sys.stderr)
        return pd.DataFrame()

    return pd.DataFrame(rows)


def fetch_swebench() -> pd.DataFrame:
    """
    Fetch SWE-bench leaderboard resolve rates.

    Scrapes the inline JSON leaderboard data embedded in https://www.swebench.com.
    Falls back to cached data if the network is unavailable.

    Returns columns: model, benchmark, score, source.
    Benchmark values: "SWE-bench Verified", "SWE-bench Lite", "SWE-bench Test",
    "SWE-bench Multimodal", "SWE-bench Multilingual", "SWE-bench Verified (bash-only)".
    Scores are resolve-rate percentages (0–100).
    Returns an empty DataFrame on total failure.
    """
    # Check cache first
    cached = load_cache(SOURCE)
    if cached is not None:
        try:
            df = pd.read_csv(io.StringIO(cached))
            if {"model", "benchmark", "score", "source"}.issubset(df.columns):
                return df
        except Exception:
            pass

    df = _scrape_website()
    if not df.empty:
        save_cache(SOURCE, df.to_csv(index=False), ext="txt")
        return df

    print("[swebench] All fetch strategies failed — returning empty DataFrame.", file=sys.stderr)
    return pd.DataFrame(columns=["model", "benchmark", "score", "source"])


if __name__ == "__main__":
    df = fetch_swebench()
    print(f"Fetched {len(df)} rows from swebench")
    print(df["benchmark"].value_counts())
    print(df.head(10))
