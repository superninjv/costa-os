"""
bfcl.py — Fetcher for Berkeley Function-Calling Leaderboard (BFCL) data.

BFCL measures how accurately LLMs can call functions/tools given natural
language instructions. It is one of the most rigorous evals for agentic and
tool-use capabilities.

Data lives in https://github.com/HuanzhiMao/BFCL-Result organised by
date-stamped directories (e.g. 2025-12-16/score/data_overall.csv).
We query the GitHub Contents API to find the latest date directory, then
fetch the CSVs from that directory.

Source repo: https://github.com/HuanzhiMao/BFCL-Result
Update frequency: continuous (community submissions).
"""

import io
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from _cache import load_cache, save_cache

SOURCE = "bfcl"
GITHUB_API_CONTENTS = "https://api.github.com/repos/HuanzhiMao/BFCL-Result/contents/"
RAW_BASE = "https://raw.githubusercontent.com/HuanzhiMao/BFCL-Result/main"

# CSV filenames inside each date/score/ directory -> benchmark label
CSV_FILES = {
    "data_overall.csv": "BFCL Overall",
    "data_live.csv": "BFCL Live",
    "data_non_live.csv": "BFCL Non-Live",
    "data_multi_turn.csv": "BFCL Multi-Turn",
}


def _get(url: str, timeout: int = 30) -> requests.Response | None:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        print(f"[bfcl] HTTP error {url}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[bfcl] Error {url}: {exc}", file=sys.stderr)
        return None


def _find_latest_date_dir() -> str | None:
    """
    Query the GitHub Contents API to find the most recent date-stamped
    directory in the BFCL-Result repo.  Directories are named YYYY-MM-DD.
    """
    resp = _get(GITHUB_API_CONTENTS)
    if resp is None:
        return None
    try:
        entries = resp.json()
        dirs = [
            e["name"]
            for e in entries
            if e["type"] == "dir" and len(e["name"]) == 10 and e["name"][4] == "-"
        ]
        if not dirs:
            return None
        return sorted(dirs)[-1]  # lexicographic sort == chronological for YYYY-MM-DD
    except Exception as exc:
        print(f"[bfcl] Failed to parse directory listing: {exc}", file=sys.stderr)
        return None


def _parse_bfcl_csv(raw: bytes, benchmark_label: str) -> pd.DataFrame:
    """
    Parse a BFCL score CSV.

    The repo CSV has columns including:
      Rank, Overall Acc, Model, Model Link, ...
    We want Model (string) and Overall Acc (percentage string like "77.47%").
    Fall back to heuristics for other column name variants.
    """
    df_raw = pd.read_csv(io.BytesIO(raw))
    df_raw.columns = [c.strip() for c in df_raw.columns]

    col_lower = {c.lower().replace(" ", "_"): c for c in df_raw.columns}

    model_keys = ["model", "model_name", "name"]
    score_keys = [
        "overall_acc",
        "overall_accuracy",
        "overall_score",
        "live_overall_acc",
        "non-live_overall_acc",
        "multi_turn_overall_acc",
        "accuracy",
        "score",
        "total_score",
        "final_score",
        "avg_accuracy",
    ]

    model_col = next((col_lower[k] for k in model_keys if k in col_lower), None)
    score_col = next((col_lower[k] for k in score_keys if k in col_lower), None)

    if model_col is None or score_col is None:
        str_cols = [c for c in df_raw.columns if df_raw[c].dtype == object]
        num_cols = [
            c for c in df_raw.columns if pd.api.types.is_numeric_dtype(df_raw[c])
        ]
        if str_cols and num_cols:
            model_col = str_cols[0]
            score_col = num_cols[-1]
        else:
            print(
                f"[bfcl] Cannot identify model/score columns in {benchmark_label}: "
                f"{list(df_raw.columns)}",
                file=sys.stderr,
            )
            return pd.DataFrame()

    # Scores are percentage strings like "77.47%" — strip the % sign
    raw_scores = df_raw[score_col].astype(str).str.replace("%", "", regex=False).str.strip()

    out = pd.DataFrame(
        {
            "model": df_raw[model_col].astype(str).str.strip(),
            "benchmark": benchmark_label,
            "score": pd.to_numeric(raw_scores, errors="coerce"),
            "source": SOURCE,
        }
    )
    return out.dropna(subset=["score"])


def _fetch_csvs_for_dir(date_dir: str) -> pd.DataFrame:
    """Fetch all known score CSVs from a given date directory."""
    frames = []
    for filename, label in CSV_FILES.items():
        url = f"{RAW_BASE}/{date_dir}/score/{filename}"
        resp = _get(url)
        if resp is None:
            print(f"[bfcl] Missing {filename} in {date_dir}", file=sys.stderr)
            continue
        df = _parse_bfcl_csv(resp.content, label)
        if not df.empty:
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def fetch_bfcl() -> pd.DataFrame:
    """
    Fetch Berkeley Function-Calling Leaderboard scores.

    Dynamically finds the most recent date-stamped results directory via the
    GitHub Contents API, then downloads the four score CSVs from that directory.

    Falls back to cached data if the network is unavailable.

    Returns columns: model, benchmark, score, source.
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

    # Find latest date directory
    date_dir = _find_latest_date_dir()
    if date_dir is None:
        print("[bfcl] Could not determine latest date directory.", file=sys.stderr)
        return pd.DataFrame(columns=["model", "benchmark", "score", "source"])

    print(f"[bfcl] Using date directory: {date_dir}", file=sys.stderr)
    df = _fetch_csvs_for_dir(date_dir)

    if df.empty:
        print("[bfcl] No data retrieved.", file=sys.stderr)
        return pd.DataFrame(columns=["model", "benchmark", "score", "source"])

    # Cache the result
    save_cache(SOURCE, df.to_csv(index=False), ext="txt")
    return df


if __name__ == "__main__":
    df = fetch_bfcl()
    print(f"Fetched {len(df)} rows from bfcl")
    print(df["benchmark"].value_counts())
    print(df.head(10))
