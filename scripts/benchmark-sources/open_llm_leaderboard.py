"""
open_llm_leaderboard.py — Fetcher for HuggingFace Open LLM Leaderboard v2.

The Open LLM Leaderboard (v2) evaluates open-weight models across six
rigorous benchmarks:
  - BBH (BIG-Bench Hard): complex reasoning tasks
  - GPQA: PhD-level science questions (Diamond subset)
  - MATH-Hard: competition-level mathematics
  - MMLU-Pro: multi-domain knowledge (enhanced version)
  - IFEval: instruction-following accuracy
  - MUSR: multi-step soft reasoning

Note: This leaderboard covers open-weight models only (Qwen, Llama, Mistral,
Phi, Gemma, etc.). Proprietary models (Claude, GPT-4) are NOT included.

Source: HuggingFace Datasets API — plain HTTP, no `datasets` library required.
Update frequency: continuous (community submissions).
"""

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "ai-router" / "benchmarks" / "raw" / "open_llm_leaderboard"
SOURCE = "open_llm_leaderboard"

# The Open LLM Leaderboard v2 is a Docker Space with a live backend API.
# The HF Space subdomain serves the backend directly.
# Note: the /api/leaderboard endpoint returns all ~4500+ entries as JSON.
HF_SPACE_API = (
    "https://open-llm-leaderboard-open-llm-leaderboard.hf.space/api/leaderboard"
)

# Field names in the Space API JSON response (one object per model)
SPACE_API_MODEL_FIELD = "fullname"
SPACE_API_BENCHMARK_FIELDS = {
    "Average ⬆️": "Open LLM Average",
    "IFEval": "IFEval",
    "BBH": "BBH",
    "MATH Lvl 5": "MATH-Hard",
    "GPQA": "GPQA",
    "MUSR": "MUSR",
    "MMLU-PRO": "MMLU-Pro",
}

# Benchmark names used in the leaderboard
BENCHMARK_COLS = {
    "bbh": "BBH",
    "gpqa": "GPQA",
    "math_hard": "MATH-Hard",
    "mmlu_pro": "MMLU-Pro",
    "ifeval": "IFEval",
    "musr": "MUSR",
    "average": "Open LLM Average",
}

# Column aliases that appear in various versions of the dataset
BENCHMARK_ALIASES: dict[str, list[str]] = {
    "BBH": ["bbh", "BBH", "bbh_cot_fewshot", "big_bench_hard"],
    "GPQA": ["gpqa", "GPQA", "gpqa_diamond", "GPQA Diamond"],
    "MATH-Hard": ["math_hard", "MATH-Hard", "math_lvl5", "MATH_Hard", "hendrycks_math"],
    "MMLU-Pro": ["mmlu_pro", "MMLU-Pro", "mmlu_pro_cot", "MMLU_Pro"],
    "IFEval": ["ifeval", "IFEval", "instruction_following", "IFEval_Avg"],
    "MUSR": ["musr", "MUSR", "multi_step_reasoning"],
    "Open LLM Average": ["average", "avg", "Average", "overall", "score"],
}


def _cache_path(filename: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / filename


def _stamped(label: str, ext: str = "csv") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    safe = label.lower().replace(" ", "_").replace("-", "_")
    return f"{safe}_{stamp}.{ext}"


def _get(url: str, timeout: int = 30) -> requests.Response | None:
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "costa-os-benchmarks/1.0"},
        )
        resp.raise_for_status()
        return resp
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 404):
            return None
        print(f"[open_llm_leaderboard] HTTP error {url}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[open_llm_leaderboard] Error {url}: {exc}", file=sys.stderr)
        return None


def _find_col(df_cols: list[str], aliases: list[str]) -> str | None:
    """Return the first column name that matches any alias (case-insensitive)."""
    col_lower = {c.lower().replace(" ", "_").replace("-", "_"): c for c in df_cols}
    for alias in aliases:
        norm = alias.lower().replace(" ", "_").replace("-", "_")
        if norm in col_lower:
            return col_lower[norm]
    return None


def _normalise_leaderboard_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Convert a wide-format leaderboard DataFrame (one row per model, columns
    for each benchmark) into a long-format DataFrame with columns:
    model, benchmark, score, source.
    """
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    # Find model column
    model_col = _find_col(
        list(df_raw.columns),
        ["model", "model_name", "name", "full_model_name", "model_id"],
    )
    if model_col is None:
        str_cols = [c for c in df_raw.columns if df_raw[c].dtype == object]
        model_col = str_cols[0] if str_cols else None

    if model_col is None:
        print("[open_llm_leaderboard] Cannot identify model column.", file=sys.stderr)
        return pd.DataFrame()

    rows = []
    for _, row in df_raw.iterrows():
        model_name = str(row[model_col]).strip()
        if not model_name or model_name.lower() in ("nan", "none", ""):
            continue

        for bench_label, aliases in BENCHMARK_ALIASES.items():
            matched_col = _find_col(list(df_raw.columns), aliases)
            if matched_col is None:
                continue
            try:
                score = float(row[matched_col])
                if pd.isna(score):
                    continue
                rows.append(
                    {
                        "model": model_name,
                        "benchmark": bench_label,
                        "score": score,
                        "source": SOURCE,
                    }
                )
            except (ValueError, TypeError):
                continue

    return pd.DataFrame(rows)


def _parse_json_results(raw: bytes) -> pd.DataFrame:
    """
    Parse the HuggingFace dataset API JSON response.

    The API returns a list of result objects or a nested structure; we handle
    both the dataset metadata format and embedded CSV/parquet references.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return pd.DataFrame()

    # The API might return metadata with parquet file links
    if isinstance(data, dict):
        # Try to find embedded results data
        for key in ["rows", "data", "results", "leaderboard"]:
            if key in data and isinstance(data[key], list):
                # Try to convert to DataFrame
                try:
                    df_raw = pd.DataFrame(data[key])
                    df = _normalise_leaderboard_df(df_raw)
                    if not df.empty:
                        return df
                except Exception:
                    pass

        # Check for parquet URLs we could fetch
        parquet_urls = []
        for key in ["parquet_files", "files", "splits"]:
            if key in data:
                entries = data[key]
                if isinstance(entries, list):
                    for entry in entries:
                        url = (
                            entry.get("url")
                            or entry.get("filename")
                            or (entry if isinstance(entry, str) else None)
                        )
                        if url and ".parquet" in str(url):
                            parquet_urls.append(str(url))

        for url in parquet_urls[:3]:  # Limit to first 3 files
            df = _fetch_parquet(url)
            if not df.empty:
                return df

    elif isinstance(data, list):
        try:
            df_raw = pd.DataFrame(data)
            return _normalise_leaderboard_df(df_raw)
        except Exception:
            pass

    return pd.DataFrame()


def _fetch_parquet(url: str) -> pd.DataFrame:
    """Download and parse a parquet file (requires pyarrow or fastparquet)."""
    try:
        import pyarrow.parquet as pq  # type: ignore
    except ImportError:
        try:
            import fastparquet  # type: ignore  # noqa: F401
        except ImportError:
            return pd.DataFrame()

    resp = _get(url, timeout=60)
    if resp is None:
        return pd.DataFrame()

    try:
        import pyarrow.parquet as pq
        table = pq.read_table(io.BytesIO(resp.content))
        df_raw = table.to_pandas()
        return _normalise_leaderboard_df(df_raw)
    except Exception:
        pass

    try:
        df_raw = pd.read_parquet(io.BytesIO(resp.content))
        return _normalise_leaderboard_df(df_raw)
    except Exception as exc:
        print(f"[open_llm_leaderboard] Parquet parse failed: {exc}", file=sys.stderr)
        return pd.DataFrame()


def _try_hf_space_api() -> pd.DataFrame:
    """
    Fetch leaderboard data from the Open LLM Leaderboard v2 HuggingFace Space.

    The Space runs a live FastAPI backend at:
      https://open-llm-leaderboard-open-llm-leaderboard.hf.space/api/leaderboard

    Returns all ~4500+ model entries as a JSON list with fields including
    'fullname', 'Average ⬆️', 'IFEval', 'BBH', 'MATH Lvl 5', 'GPQA',
    'MUSR', 'MMLU-PRO'.
    """
    resp = _get(HF_SPACE_API, timeout=60)
    if resp is None:
        return pd.DataFrame()

    try:
        data = json.loads(resp.content)
    except json.JSONDecodeError:
        return pd.DataFrame()

    if not isinstance(data, list) or not data:
        return pd.DataFrame()

    rows = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        model_name = entry.get(SPACE_API_MODEL_FIELD, "")
        if not model_name or str(model_name).lower() in ("nan", "none", ""):
            continue

        for api_field, bench_label in SPACE_API_BENCHMARK_FIELDS.items():
            raw_score = entry.get(api_field)
            if raw_score is None:
                continue
            try:
                score = float(raw_score)
                if pd.isna(score):
                    continue
                rows.append(
                    {
                        "model": str(model_name).strip(),
                        "benchmark": bench_label,
                        "score": score,
                        "source": SOURCE,
                    }
                )
            except (ValueError, TypeError):
                continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # Cache as CSV for offline fallback
    try:
        cache_file = _cache_path(_stamped("open_llm_leaderboard"))
        df.to_csv(cache_file, index=False)
    except Exception:
        pass
    return df


def _try_hf_api() -> pd.DataFrame:
    """Try the HuggingFace dataset API endpoint (legacy, kept as fallback)."""
    resp = _get(HF_SPACE_API, timeout=60)
    if resp is None:
        return pd.DataFrame()

    # The API may return metadata with parquet file references
    df = _parse_json_results(resp.content)
    if not df.empty:
        _cache_path(_stamped("open_llm_api", "json")).write_bytes(resp.content)

    return df


def _try_hf_csv_paths() -> pd.DataFrame:
    """Kept as no-op fallback — the old CSV paths no longer exist."""
    return pd.DataFrame()


def _try_hf_parquet_auto() -> pd.DataFrame:
    """Kept as no-op fallback — the old parquet paths no longer exist."""
    return pd.DataFrame()


def _try_cache() -> pd.DataFrame | None:
    """Return the most recent cached data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(CACHE_DIR.glob("open_llm_*.csv"), reverse=True)
    for f in files[:1]:
        try:
            df = pd.read_csv(f)
            if {"model", "benchmark", "score", "source"}.issubset(df.columns):
                print(f"[open_llm_leaderboard] Using cache: {f.name}", file=sys.stderr)
                return df
        except Exception:
            pass
    return None


def fetch_open_llm_leaderboard() -> pd.DataFrame:
    """
    Fetch HuggingFace Open LLM Leaderboard v2 scores.

    Covers open-weight models only. Benchmarks: BBH, GPQA, MATH-Hard,
    MMLU-Pro, IFEval, MUSR, and aggregate average.

    Uses plain HTTP requests only — no `datasets` library dependency.

    Tries (in order):
      1. HuggingFace Space live API (open-llm-leaderboard Docker Space backend)
      2. Local cache (CSV written by previous successful fetch)

    Returns columns: model, benchmark, score, source.
    Returns an empty DataFrame on total failure.
    """
    df = _try_hf_space_api()
    if not df.empty:
        return df

    df = _try_cache()
    if df is not None:
        return df

    print(
        "[open_llm_leaderboard] All fetch strategies failed — returning empty DataFrame.",
        file=sys.stderr,
    )
    return pd.DataFrame(columns=["model", "benchmark", "score", "source"])


if __name__ == "__main__":
    df = fetch_open_llm_leaderboard()
    print(f"Fetched {len(df)} rows from open_llm_leaderboard")
    print(df["benchmark"].value_counts())
    print(df.head(10))
