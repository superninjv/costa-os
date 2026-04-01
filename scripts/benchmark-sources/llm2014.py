"""
llm2014.py — Fetcher for llm2014 benchmark data (Chinese LLM leaderboard).

llm2014 is a rigorous Chinese-language benchmark that evaluates models across:
  - Logic: multi-step logical reasoning (极限分数 = ceiling score used)
  - Code: multi-round coding tasks (多轮总分 = multi-round total used)
  - Code v3: vibe coding / full application builds
  - Vision: multimodal vision-language tasks

Data is published monthly as dated CSVs in a GitHub repo. Headers are in
Chinese; this module maps them to English. Primarily covers frontier models
(both Chinese and international).

Source repo: https://github.com/llm2014/llm_benchmark
Update frequency: monthly.
"""

import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "ai-router" / "benchmarks" / "raw" / "llm2014"
SOURCE = "llm2014"

BASE_RAW = "https://raw.githubusercontent.com/llm2014/llm_benchmark/main/docs/data"

# Category → (subdirectory, benchmark_label, primary_score_column, fallback_months)
CATEGORIES = {
    "logic": {
        "subdir": "logic",
        "label": "llm2014-logic",
        "primary_col_cn": "极限分数",
        "primary_col_aliases": ["ceiling_score", "极限分数", "最高分", "max_score"],
        "months": ["2026-03", "2026-02", "2026-01", "2025-12", "2025-11"],
    },
    "code": {
        "subdir": "code",
        "label": "llm2014-code",
        "primary_col_cn": "多轮总分",
        "primary_col_aliases": ["multi_round_total", "多轮总分", "总分", "total_score"],
        "months": ["2026-02", "2026-01", "2025-12", "2025-11", "2025-10"],
    },
    "code_v3": {
        "subdir": "code_v3",
        "label": "llm2014-code-v3",
        "primary_col_cn": "多轮总分",
        "primary_col_aliases": ["multi_round_total", "多轮总分", "总分", "total_score"],
        "months": ["2026-01", "2025-12", "2025-11", "2025-10"],
    },
    "vision": {
        "subdir": "vision",
        "label": "llm2014-vision",
        "primary_col_cn": "极限分数",
        "primary_col_aliases": ["ceiling_score", "极限分数", "最高分", "score"],
        "months": ["2025-09", "2025-08", "2025-07", "2025-06"],
    },
}

# Chinese → English column mapping (normalisation)
CN_TO_EN = {
    "模型": "model",
    "极限分数": "ceiling_score",
    "中位分数": "median_score",
    "多轮总分": "multi_round_total",
    "总分": "total_score",
    "视觉": "vision_score",
    "代码": "code_score",
    "逻辑": "logic_score",
    "得分": "score",
    "排名": "rank",
    "最高分": "max_score",
    "平均分": "average_score",
}


def _cache_path(filename: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / filename


def _stamped(label: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    safe = label.replace("-", "_")
    return f"{safe}_{stamp}.csv"


def _get(url: str, timeout: int = 20) -> requests.Response | None:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        print(f"[llm2014] HTTP error {url}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[llm2014] Error {url}: {exc}", file=sys.stderr)
        return None


def _get_latest_csv(base_url: str, subdir: str, months: list[str]) -> tuple[bytes, str] | None:
    """
    Fetch the latest available CSV from a date-based GitHub directory.

    Tries each month string in `months` (newest first) until one succeeds.
    Returns (content_bytes, month_used) or None.
    """
    for month in months:
        url = f"{base_url}/{subdir}/{month}.csv"
        resp = _get(url)
        if resp is not None:
            return resp.content, month

    # Also try without the subdir separator (flat structure)
    for month in months:
        url = f"{base_url}/{month}.csv"
        resp = _get(url)
        if resp is not None:
            return resp.content, month

    return None


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Translate Chinese column headers to English and strip whitespace."""
    renamed = {}
    for col in df.columns:
        col_stripped = str(col).strip()
        renamed[col] = CN_TO_EN.get(col_stripped, col_stripped.lower().replace(" ", "_"))
    return df.rename(columns=renamed)


def _find_model_col(df: pd.DataFrame) -> str | None:
    for candidate in ["model", "模型", "name", "system", "model_name"]:
        if candidate in df.columns:
            return candidate
    # First object/string column
    for col in df.columns:
        if df[col].dtype == object:
            return col
    return None


def _find_score_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for alias in aliases:
        # Check pre-normalisation alias
        if alias in df.columns:
            return alias
        # Check normalised version
        en = CN_TO_EN.get(alias, alias.lower().replace(" ", "_"))
        if en in df.columns:
            return en
    # Fall back: last numeric column
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    return num_cols[-1] if num_cols else None


def _parse_category_csv(
    raw: bytes,
    label: str,
    score_aliases: list[str],
) -> pd.DataFrame:
    """Parse a single llm2014 CSV into the normalised format."""
    # Try UTF-8 first, then GBK (common for Chinese CSVs)
    for encoding in ["utf-8", "utf-8-sig", "gbk", "gb2312"]:
        try:
            df_raw = pd.read_csv(io.BytesIO(raw), encoding=encoding)
            break
        except (UnicodeDecodeError, Exception):
            continue
    else:
        print(f"[llm2014] Could not decode CSV for {label}", file=sys.stderr)
        return pd.DataFrame()

    df_raw.columns = [str(c).strip() for c in df_raw.columns]
    df = _normalise_columns(df_raw)

    model_col = _find_model_col(df)
    score_col = _find_score_col(df, score_aliases)

    if model_col is None or score_col is None:
        print(
            f"[llm2014] Cannot identify model/score cols for {label}: {list(df.columns)}",
            file=sys.stderr,
        )
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "model": df[model_col].astype(str).str.strip(),
            "benchmark": label,
            "score": pd.to_numeric(df[score_col], errors="coerce"),
            "source": SOURCE,
        }
    )
    return out.dropna(subset=["score"])


def _try_cache(label: str) -> pd.DataFrame | None:
    """Return most recent cached CSV for a given label."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = label.replace("-", "_")
    files = sorted(CACHE_DIR.glob(f"{safe}_*.csv"), reverse=True)
    for f in files[:1]:
        try:
            df = pd.read_csv(f)
            if {"model", "benchmark", "score", "source"}.issubset(df.columns):
                print(f"[llm2014] Using cache: {f.name}", file=sys.stderr)
                return df
        except Exception:
            pass
    return None


def _fetch_category(cat_key: str) -> pd.DataFrame:
    """Fetch data for one category; fall back to cache on failure."""
    meta = CATEGORIES[cat_key]
    subdir = meta["subdir"]
    label = meta["label"]
    score_aliases = meta["primary_col_aliases"]
    months = meta["months"]

    result = _get_latest_csv(BASE_RAW, subdir, months)
    if result is not None:
        raw, month_used = result
        df = _parse_category_csv(raw, label, score_aliases)
        if not df.empty:
            cache_name = _stamped(label)
            _cache_path(cache_name).write_bytes(raw)
            print(f"[llm2014] Fetched {label} ({month_used}): {len(df)} rows", file=sys.stderr)
            return df

    # Fall back to cache
    cached = _try_cache(label)
    if cached is not None:
        return cached

    print(f"[llm2014] No data available for {label}", file=sys.stderr)
    return pd.DataFrame(columns=["model", "benchmark", "score", "source"])


def fetch_llm2014() -> pd.DataFrame:
    """
    Fetch llm2014 benchmark scores (Chinese LLM leaderboard).

    Downloads the latest available monthly CSVs for each category:
      - llm2014-logic    (极限分数 / ceiling score)
      - llm2014-code     (多轮总分 / multi-round total)
      - llm2014-code-v3  (vibe coding / full app builds)
      - llm2014-vision   (multimodal vision tasks)

    Handles Chinese UTF-8/GBK headers transparently.

    Returns columns: model, benchmark, score, source.
    Returns an empty DataFrame only if all categories and caches are unavailable.
    """
    frames = []
    for cat_key in CATEGORIES:
        df = _fetch_category(cat_key)
        if not df.empty:
            frames.append(df)

    if not frames:
        print("[llm2014] No data retrieved from any category.", file=sys.stderr)
        return pd.DataFrame(columns=["model", "benchmark", "score", "source"])

    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    df = fetch_llm2014()
    print(f"Fetched {len(df)} rows from llm2014")
    print(df["benchmark"].value_counts())
    print(df.head(10))
