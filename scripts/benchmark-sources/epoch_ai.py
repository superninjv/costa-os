"""
epoch_ai.py — Fetcher for Epoch AI benchmark data.

Epoch AI runs rigorous evals of frontier models across benchmarks like
GPQA Diamond, MATH, HumanEval, SWE-bench, Chess Puzzles, and more.
They publish a unified CSV at https://epoch.ai/data/benchmarks.csv
that contains all evaluation runs with model name, task, and score.

Source: https://epoch.ai/data/benchmarks.csv
Update frequency: continuous as new evals are published.
"""

import io
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from _cache import load_cache, save_cache

SOURCE = "epoch_ai"

# Epoch AI publishes a unified CSV of all benchmark results
EPOCH_CSV_URL = "https://epoch.ai/data/benchmarks.csv"


def _fetch_csv() -> pd.DataFrame | None:
    """Download and parse the Epoch AI benchmarks CSV."""
    try:
        resp = requests.get(EPOCH_CSV_URL, timeout=60)
        resp.raise_for_status()
        raw = resp.content

        df_raw = pd.read_csv(io.BytesIO(raw), low_memory=False)

        # Normalise whitespace in column names (but preserve exact case)
        df_raw.columns = [c.strip() for c in df_raw.columns]
        cols = set(df_raw.columns)

        # Use exact column names because the CSV has duplicate-when-lowercased pairs
        # (e.g. both "task" and "Task", "model" and "Model").
        # Priority order for model: "Display name" > "model" > "Model"
        if "Display name" in cols:
            model_col = "Display name"
        elif "model" in cols:
            model_col = "model"
        elif "Model" in cols:
            model_col = "Model"
        else:
            str_cols = [c for c in df_raw.columns if df_raw[c].dtype == object]
            model_col = str_cols[0] if str_cols else None

        # "task" (lowercase) = benchmark name like "GPQA diamond"
        # "Task" (uppercase) = generic domain category — we don't want that
        if "task" in cols:
            bench_col = "task"
        elif "original_task_name" in cols:
            bench_col = "original_task_name"
        else:
            bench_col = None

        # "Best score (across scorers)" is the primary score column
        if "Best score (across scorers)" in cols:
            score_col = "Best score (across scorers)"
        elif "mean_score" in cols:
            score_col = "mean_score"
        elif "best_score" in cols:
            score_col = "best_score"
        else:
            score_col = None

        if not all([model_col, bench_col, score_col]):
            print(
                f"[epoch_ai] Could not map columns. Available: {list(df_raw.columns)[:10]}",
                file=sys.stderr,
            )
            return None

        out = pd.DataFrame(
            {
                "model": df_raw[model_col].astype(str).str.strip(),
                "benchmark": df_raw[bench_col].astype(str).str.strip(),
                "score": pd.to_numeric(df_raw[score_col], errors="coerce"),
                "source": SOURCE,
            }
        )
        out = out.dropna(subset=["score"])
        out = out[out["model"].str.strip() != ""]
        out = out[out["model"] != "nan"]

        # Epoch AI uses 0-1 scale; convert to 0-100 percentage to match other sources
        out.loc[out["score"] <= 1.0, "score"] = out.loc[out["score"] <= 1.0, "score"] * 100

        return out if not out.empty else None
    except Exception as exc:
        print(f"[epoch_ai] CSV fetch failed: {exc}", file=sys.stderr)
        return None


def fetch_epoch_ai() -> pd.DataFrame:
    """
    Fetch Epoch AI benchmark scores.

    Downloads the unified CSV from https://epoch.ai/data/benchmarks.csv,
    which contains model evaluation results across GPQA Diamond, MATH,
    HumanEval, Chess Puzzles, SWE-bench, SimpleQA, and more.

    Falls back to local cache if the network is unavailable.

    Returns columns: model, benchmark, score, source.
    Scores are in the benchmark's native units (fractions 0-1 for most).
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

    df = _fetch_csv()
    if df is not None and not df.empty:
        save_cache(SOURCE, df.to_csv(index=False), ext="txt")
        return df

    print("[epoch_ai] All fetch strategies failed — returning empty DataFrame.", file=sys.stderr)
    return pd.DataFrame(columns=["model", "benchmark", "score", "source"])


if __name__ == "__main__":
    df = fetch_epoch_ai()
    print(f"Fetched {len(df)} rows from epoch_ai")
    print(df["benchmark"].value_counts().head(10))
    print(df.head(10))
