"""
chatbot_arena.py — Fetcher for Chatbot Arena (LMSYS) Elo ratings.

Chatbot Arena is a crowd-sourced human preference benchmark where users
vote between anonymous model responses. The Elo rating reflects relative
win rates across millions of conversations.

Key metrics:
  - Overall Elo (general-purpose quality)
  - Coding Elo (available as a separate leaderboard)
  - Math Elo (available as a separate leaderboard)
  - Hard Prompts Elo (subset of difficult/adversarial prompts)

Sources tried (in order):
  1. arena-hard-auto GitHub CSV data (automated proxy for human eval)
  2. HuggingFace lm-sys/chatbot-arena-leaderboard dataset
  3. LMSYS Gradio API / leaderboard page scrape
  4. Local cache

Update frequency: continuous voting, leaderboard refreshed daily.
"""

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

CACHE_DIR = Path("/home/jack/projects/costa-os/ai-router/benchmarks/raw/chatbot_arena")
SOURCE = "chatbot_arena"

# arena-hard-auto: automated GPT-4 judge proxy, highly correlated with Arena Elo
# Repo moved from lm-sys to lmarena org; leaderboard CSVs live in leaderboard/ dir
ARENA_HARD_RAW_LMARENA = "https://raw.githubusercontent.com/lmarena/arena-hard-auto/main"
ARENA_HARD_RAW_LMSYS = "https://raw.githubusercontent.com/lm-sys/arena-hard-auto/main"

ARENA_HARD_PATHS = [
    "leaderboard/arena_hard_leaderboard_20240731.csv",
    "leaderboard/arena_hard_leaderboard.csv",
    "data/arena-hard-v0.1/model_judgment/gpt-4-1106-preview_pair.jsonl",
]

# HuggingFace dataset — no datasets library needed, use raw HTTP
# lmarena-ai/arena-hard-auto-v0.1 has a parquet train split with win_rate data
HF_DATASET_BASE = "https://huggingface.co/datasets/lmarena-ai/arena-hard-auto-v0.1/resolve/main"
HF_PATHS = [
    "data/train-00000-of-00001.parquet",
]

# Older lm-sys dataset paths (fallback)
HF_DATASET_BASE_OLD = "https://huggingface.co/datasets/lm-sys/chatbot-arena-leaderboard/resolve/main"
HF_PATHS_OLD = [
    "data/elo_results_20240619.csv",
    "data/leaderboard.csv",
    "elo_results.csv",
    "leaderboard.csv",
]

LMSYS_WEBSITE = "https://leaderboard.lmsys.org"
LMSYS_API_CANDIDATES = [
    "https://leaderboard.lmsys.org/api/leaderboard",
    "https://chat.lmsys.org/api/leaderboard",
]


def _cache_path(filename: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / filename


def _stamped(label: str, ext: str = "csv") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    safe = label.lower().replace(" ", "_").replace("-", "_")
    return f"{safe}_{stamp}.{ext}"


def _get(url: str, timeout: int = 30) -> requests.Response | None:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "costa-os-benchmarks/1.0"})
        resp.raise_for_status()
        return resp
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 404):
            return None
        print(f"[chatbot_arena] HTTP error {url}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"[chatbot_arena] Error {url}: {exc}", file=sys.stderr)
        return None


def _parse_elo_csv(raw: bytes, benchmark_label: str) -> pd.DataFrame:
    """
    Parse a leaderboard CSV with Elo ratings.

    Handles multiple column naming conventions found across arena data sources.
    """
    df_raw = pd.read_csv(io.BytesIO(raw))
    df_raw.columns = [str(c).strip() for c in df_raw.columns]
    col_lower = {c.lower().replace(" ", "_"): c for c in df_raw.columns}

    model_col = next(
        (
            col_lower[k]
            for k in ["model", "model_name", "name", "system", "chatbot"]
            if k in col_lower
        ),
        None,
    )
    elo_col = next(
        (
            col_lower[k]
            for k in [
                "elo",
                "elo_rating",
                "arena_elo",
                "score",
                "rating",
                "elo_score",
                "arena_score",
                "win_rate",
                "lc_win_rate",
            ]
            if k in col_lower
        ),
        None,
    )

    if model_col is None:
        str_cols = [c for c in df_raw.columns if df_raw[c].dtype == object]
        model_col = str_cols[0] if str_cols else None

    if elo_col is None:
        num_cols = [c for c in df_raw.columns if pd.api.types.is_numeric_dtype(df_raw[c])]
        elo_col = num_cols[0] if num_cols else None

    if model_col is None or elo_col is None:
        print(
            f"[chatbot_arena] Cannot identify model/score cols: {list(df_raw.columns)}",
            file=sys.stderr,
        )
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "model": df_raw[model_col].astype(str).str.strip(),
            "benchmark": benchmark_label,
            "score": pd.to_numeric(df_raw[elo_col], errors="coerce"),
            "source": SOURCE,
        }
    )
    return out.dropna(subset=["score"])


def _parse_jsonl_arena_hard(raw: bytes) -> pd.DataFrame:
    """
    Parse arena-hard-auto JSONL pairwise judgments into win rates.
    Each line: {model: str, scores: {model2: {win: N, lose: N, tie: N}}}
    """
    win_counts: dict[str, dict] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        model_a = entry.get("model_a") or entry.get("model") or ""
        model_b = entry.get("model_b") or ""
        winner = entry.get("winner") or entry.get("result") or ""

        for m in [model_a, model_b]:
            if m and m not in win_counts:
                win_counts[m] = {"wins": 0, "total": 0}

        if model_a and model_b:
            win_counts[model_a]["total"] += 1
            win_counts[model_b]["total"] += 1
            if winner == "model_a":
                win_counts[model_a]["wins"] += 1
            elif winner == "model_b":
                win_counts[model_b]["wins"] += 1

    rows = []
    for model, counts in win_counts.items():
        if counts["total"] > 0:
            win_rate = (counts["wins"] / counts["total"]) * 100.0
            rows.append(
                {
                    "model": model.strip(),
                    "benchmark": "Chatbot Arena (Arena-Hard)",
                    "score": win_rate,
                    "source": SOURCE,
                }
            )

    return pd.DataFrame(rows)


def _parse_json_leaderboard(raw: bytes, benchmark_label: str) -> pd.DataFrame:
    """Parse a JSON leaderboard response."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return pd.DataFrame()

    rows = []
    entries = data if isinstance(data, list) else data.get("data", data.get("leaderboard", []))

    if not isinstance(entries, list):
        # Try dict-of-dicts
        if isinstance(data, dict):
            entries = [{"model": k, **v} for k, v in data.items() if isinstance(v, dict)]

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model = (
            entry.get("model")
            or entry.get("model_name")
            or entry.get("name")
            or ""
        )
        score = (
            entry.get("elo")
            or entry.get("elo_rating")
            or entry.get("arena_elo")
            or entry.get("score")
            or entry.get("rating")
        )
        if model and score is not None:
            try:
                rows.append(
                    {
                        "model": str(model).strip(),
                        "benchmark": benchmark_label,
                        "score": float(score),
                        "source": SOURCE,
                    }
                )
            except (ValueError, TypeError):
                continue

    return pd.DataFrame(rows)


def _try_arena_hard_github() -> pd.DataFrame:
    """Try arena-hard-auto GitHub data from lmarena (new) and lm-sys (old) orgs."""
    for base_url in [ARENA_HARD_RAW_LMARENA, ARENA_HARD_RAW_LMSYS]:
        for path in ARENA_HARD_PATHS:
            url = f"{base_url}/{path}"
            resp = _get(url)
            if resp is None:
                continue

            if path.endswith(".jsonl"):
                df = _parse_jsonl_arena_hard(resp.content)
            elif path.endswith(".csv"):
                df = _parse_elo_csv(resp.content, "Chatbot Arena (Arena-Hard)")
            elif path.endswith(".parquet"):
                df = _fetch_parquet_arena(resp.content)
            else:
                continue

            if not df.empty:
                _cache_path(_stamped("arena_hard")).write_bytes(resp.content)
                return df

    return pd.DataFrame()


def _fetch_parquet_arena(content: bytes) -> pd.DataFrame:
    """Parse a parquet file containing arena-hard model win rate data."""
    try:
        import pyarrow.parquet as pq
        import io as _io

        table = pq.read_table(_io.BytesIO(content))
        df_raw = table.to_pandas()
    except Exception:
        try:
            import io as _io
            df_raw = pd.read_parquet(_io.BytesIO(content))
        except Exception as exc:
            print(f"[chatbot_arena] Parquet parse failed: {exc}", file=sys.stderr)
            return pd.DataFrame()

    df_raw.columns = [str(c).strip() for c in df_raw.columns]
    col_lower = {c.lower().replace(" ", "_").replace("-", "_"): c for c in df_raw.columns}

    model_col = next(
        (col_lower[k] for k in ["model", "model_name", "name"] if k in col_lower),
        None,
    )
    score_col = next(
        (
            col_lower[k]
            for k in ["win_rate", "score", "elo", "lc_win_rate", "rating"]
            if k in col_lower
        ),
        None,
    )

    if model_col is None or score_col is None:
        str_cols = [c for c in df_raw.columns if df_raw[c].dtype == object]
        num_cols = [c for c in df_raw.columns if pd.api.types.is_numeric_dtype(df_raw[c])]
        model_col = model_col or (str_cols[0] if str_cols else None)
        score_col = score_col or (num_cols[0] if num_cols else None)

    if model_col is None or score_col is None:
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "model": df_raw[model_col].astype(str).str.strip(),
            "benchmark": "Chatbot Arena (Arena-Hard)",
            "score": pd.to_numeric(df_raw[score_col], errors="coerce"),
            "source": SOURCE,
        }
    )
    return out.dropna(subset=["score"])


def _try_hf_dataset() -> pd.DataFrame:
    """Try HuggingFace lmarena-ai/arena-hard-auto-v0.1 dataset, then old lm-sys dataset."""
    # Try newer lmarena-ai dataset first
    for path in HF_PATHS:
        url = f"{HF_DATASET_BASE}/{path}"
        resp = _get(url, timeout=60)
        if resp is None:
            continue

        if path.endswith(".parquet"):
            df = _fetch_parquet_arena(resp.content)
        else:
            df = _parse_elo_csv(resp.content, "Chatbot Arena (Elo)")
        if not df.empty:
            _cache_path(_stamped("chatbot_arena_hf")).write_bytes(resp.content)
            return df

    # Fallback: older lm-sys dataset
    for path in HF_PATHS_OLD:
        url = f"{HF_DATASET_BASE_OLD}/{path}"
        resp = _get(url)
        if resp is None:
            continue

        df = _parse_elo_csv(resp.content, "Chatbot Arena (Elo)")
        if not df.empty:
            _cache_path(_stamped("chatbot_arena_hf")).write_bytes(resp.content)
            return df

    return pd.DataFrame()


def _try_lmsys_api() -> pd.DataFrame:
    """Try LMSYS API candidates."""
    for api_url in LMSYS_API_CANDIDATES:
        resp = _get(api_url, timeout=15)
        if resp is None:
            continue

        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type:
            df = _parse_json_leaderboard(resp.content, "Chatbot Arena (Elo)")
        else:
            df = _parse_elo_csv(resp.content, "Chatbot Arena (Elo)")

        if not df.empty:
            return df

    return pd.DataFrame()


def _try_lmsys_website() -> pd.DataFrame:
    """Scrape the LMSYS leaderboard website HTML tables."""
    resp = _get(LMSYS_WEBSITE, timeout=20)
    if resp is None:
        return pd.DataFrame()

    try:
        tables = pd.read_html(io.StringIO(resp.text))
        for table in tables:
            table.columns = [str(c).strip() for c in table.columns]
            df = _parse_elo_csv(table.to_csv(index=False).encode(), "Chatbot Arena (Elo)")
            if not df.empty:
                return df
    except Exception as exc:
        print(f"[chatbot_arena] Website scrape failed: {exc}", file=sys.stderr)

    return pd.DataFrame()


def _try_cache() -> pd.DataFrame | None:
    """Return the most recent cached data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for pattern in ["chatbot_arena_*.csv", "arena_hard_*.csv", "arena_hard_*.jsonl"]:
        files = sorted(CACHE_DIR.glob(pattern), reverse=True)
        for f in files[:1]:
            try:
                if f.suffix == ".csv":
                    df = pd.read_csv(f)
                    if {"model", "benchmark", "score", "source"}.issubset(df.columns):
                        print(f"[chatbot_arena] Using cache: {f.name}", file=sys.stderr)
                        frames.append(df)
                elif f.suffix == ".jsonl":
                    df = _parse_jsonl_arena_hard(f.read_bytes())
                    if not df.empty:
                        print(f"[chatbot_arena] Using cache: {f.name}", file=sys.stderr)
                        frames.append(df)
            except Exception:
                pass

    return pd.concat(frames, ignore_index=True) if frames else None


def fetch_chatbot_arena() -> pd.DataFrame:
    """
    Fetch Chatbot Arena Elo ratings.

    Tries (in order):
      1. arena-hard-auto GitHub (CSV/JSONL)
      2. HuggingFace lm-sys dataset (plain HTTP)
      3. LMSYS API candidates
      4. LMSYS website scrape
      5. Local cache

    Returns columns: model, benchmark, score, source.
    Score represents Elo rating (typical range 800–1300) or win rate
    depending on data source.
    Returns an empty DataFrame on total failure.
    """
    df = _try_arena_hard_github()
    if not df.empty:
        return df

    df = _try_hf_dataset()
    if not df.empty:
        return df

    df = _try_lmsys_api()
    if not df.empty:
        return df

    df = _try_lmsys_website()
    if not df.empty:
        return df

    df = _try_cache()
    if df is not None:
        return df

    print("[chatbot_arena] All fetch strategies failed — returning empty DataFrame.", file=sys.stderr)
    return pd.DataFrame(columns=["model", "benchmark", "score", "source"])


if __name__ == "__main__":
    df = fetch_chatbot_arena()
    print(f"Fetched {len(df)} rows from chatbot_arena")
    print(df["benchmark"].value_counts())
    print(df.head(10))
