"""
livebench.py — Fetcher for LiveBench leaderboard data.

LiveBench is a contamination-free benchmark that generates new questions monthly
from recently published papers, news, and data. It prevents memorisation-based
inflation by ensuring test data post-dates model training cuts.

Categories: Coding, Math, Reasoning, Language, Data Analysis, Instruction Following

Data source: HuggingFace parquet dataset livebench/model_judgment
  https://huggingface.co/datasets/livebench/model_judgment

We compute per-category and overall average scores by aggregating the
model_judgment parquet file (question-level scores per model).

Update frequency: monthly (new question sets).
"""

import io
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from _cache import load_cache, save_cache

SOURCE = "livebench"

# HuggingFace parquet file for livebench/model_judgment
# This file contains question-level scores for all models across all tasks
HF_PARQUET_URL = (
    "https://huggingface.co/datasets/livebench/model_judgment"
    "/resolve/refs%2Fconvert%2Fparquet/default/leaderboard/0000.parquet"
)

# Map raw category values -> human-readable benchmark labels
CATEGORY_LABEL_MAP = {
    "coding": "Coding",
    "math": "Math",
    "reasoning": "Reasoning",
    "language": "Language",
    "data_analysis": "Data Analysis",
    "instruction_following": "Instruction Following",
}


def _fetch_parquet() -> pd.DataFrame | None:
    """Download and parse the livebench model_judgment parquet file."""
    try:
        resp = requests.get(HF_PARQUET_URL, timeout=120)
        resp.raise_for_status()
        df_raw = pd.read_parquet(io.BytesIO(resp.content))
        return df_raw
    except ImportError:
        print(
            "[livebench] pyarrow not installed — run: pip install pyarrow",
            file=sys.stderr,
        )
        return None
    except Exception as exc:
        print(f"[livebench] Parquet fetch failed: {exc}", file=sys.stderr)
        return None


def _aggregate(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate question-level scores to per-model per-category averages.

    Input columns expected: model, task, score, category, question_id
    Output: model, benchmark, score, source  (one row per model × category + overall)
    """
    if df_raw.empty:
        return pd.DataFrame()

    # Normalise category column
    if "category" not in df_raw.columns:
        print("[livebench] 'category' column not found in parquet.", file=sys.stderr)
        return pd.DataFrame()

    rows = []

    # Per-category averages
    by_model_cat = (
        df_raw.groupby(["model", "category"])["score"].mean().reset_index()
    )
    for _, row in by_model_cat.iterrows():
        cat_raw = str(row["category"]).lower().replace(" ", "_")
        label = CATEGORY_LABEL_MAP.get(cat_raw, str(row["category"]).title())
        rows.append(
            {
                "model": str(row["model"]).strip(),
                "benchmark": f"LiveBench/{label}",
                "score": float(row["score"]) * 100.0,  # parquet stores 0-1, convert to %
                "source": SOURCE,
            }
        )

    # Overall average across all categories
    overall = df_raw.groupby("model")["score"].mean().reset_index()
    for _, row in overall.iterrows():
        rows.append(
            {
                "model": str(row["model"]).strip(),
                "benchmark": "LiveBench Average",
                "score": float(row["score"]) * 100.0,
                "source": SOURCE,
            }
        )

    out = pd.DataFrame(rows)
    out = out[out["model"].str.strip() != ""]
    out = out[out["model"] != "nan"]
    return out


def fetch_livebench() -> pd.DataFrame:
    """
    Fetch LiveBench leaderboard scores.

    Downloads the livebench/model_judgment parquet file from HuggingFace and
    aggregates question-level scores into per-model per-category averages.

    Falls back to cached data if the network is unavailable.

    Returns columns: model, benchmark, score, source.
    Benchmark values: "LiveBench/Coding", "LiveBench/Math", etc., plus
    "LiveBench Average" for the overall mean.
    Scores are in percentage points (0-100).
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

    df_raw = _fetch_parquet()
    if df_raw is None:
        print("[livebench] All fetch strategies failed — returning empty DataFrame.", file=sys.stderr)
        return pd.DataFrame(columns=["model", "benchmark", "score", "source"])

    df = _aggregate(df_raw)
    if df.empty:
        print("[livebench] Aggregation produced no rows.", file=sys.stderr)
        return pd.DataFrame(columns=["model", "benchmark", "score", "source"])

    save_cache(SOURCE, df.to_csv(index=False), ext="txt")
    return df


if __name__ == "__main__":
    df = fetch_livebench()
    print(f"Fetched {len(df)} rows from livebench")
    print(df["benchmark"].value_counts())
    print(df.head(10))
