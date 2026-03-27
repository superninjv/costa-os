"""
Benchmark fetcher: WebDev Arena ratings from arena.ai
Primary URL: https://arena.ai/leaderboard

The WebDev Arena has migrated to arena.ai (web.lmarena.ai now redirects there).
The leaderboard page embeds all model data in Next.js RSC (self.__next_f.push)
format.  Each model object has a 'rankByModality' field with a 'webdev' key
giving its WebDev rank, and a top-level 'rank' (overall rank).

Since only rank (not raw Elo score) is available from this page, we use
inverse rank as the score so higher-ranked models sort first:
    score = 1000 - rank   (lower rank number = better = higher score)

Benchmark name: "WebDev Arena Rank"

Extraction strategy (in order):
  1. Check local cache.
  2. Fetch arena.ai/leaderboard HTML; decode self.__next_f.push() payloads;
     find 'initialModels' array; extract models with rankByModality.webdev.
  3. Attempt HuggingFace dataset API for lmarena-ai datasets.
  4. Attempt arena API endpoints.
  5. GitHub raw data files.
  6. If all fail, return empty DataFrame.

Run standalone:
    python3 scripts/benchmark-sources/webdev_arena.py
"""

import sys
import json
import re
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from _cache import load_cache, save_cache

SOURCE = "webdev_arena"
BENCHMARK_NAME = "WebDev Arena Rank"
TIMEOUT = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
JSON_HEADERS = {**HEADERS, "Accept": "application/json"}

# arena.ai is the current home; web.lmarena.ai now redirects here
PRIMARY_URL = "https://arena.ai/leaderboard"
FALLBACK_URLS = [
    "https://lmarena.ai/leaderboard",  # also redirects to arena.ai
]

HF_DATASET_URLS = [
    "https://datasets-server.huggingface.co/rows?dataset=lmarena-ai%2Fwebdev-arena-results&split=train&offset=0&limit=100",
    "https://datasets-server.huggingface.co/rows?dataset=lmarena-ai%2Fwebdev-arena&split=train&offset=0&limit=100",
    "https://datasets-server.huggingface.co/rows?dataset=lmsys%2Fchatbot-arena-leaderboard&split=train&offset=0&limit=100",
]

ARENA_API_URLS = [
    "https://arena.ai/api/leaderboard",
    "https://arena.ai/api/leaderboard/webdev",
    "https://lmarena.ai/api/leaderboard",
    "https://lmarena.ai/api/webdev/leaderboard",
]

GITHUB_RAW_URLS = [
    "https://raw.githubusercontent.com/lm-sys/arena-hard-auto/main/data/arena_hard_leaderboard.json",
    "https://raw.githubusercontent.com/lm-sys/arena-hard-auto/main/leaderboard.json",
    "https://raw.githubusercontent.com/lm-sys/arena-hard-auto/main/results/leaderboard.json",
]

EMPTY_DF = pd.DataFrame(columns=["model", "benchmark", "score", "source"])


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fetch_arena_html() -> str | None:
    """Fetch arena.ai/leaderboard HTML with caching."""
    cached = load_cache(SOURCE)
    if cached:
        return cached

    for url in [PRIMARY_URL] + FALLBACK_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if resp.ok:
                html = resp.text
                save_cache(SOURCE, html, ext="html")
                return html
        except requests.RequestException as exc:
            print(f"[{SOURCE}] Page fetch error ({url}): {exc}", file=sys.stderr)

    return None


def _extract_from_arena_html(html: str) -> list[dict]:
    """
    arena.ai uses Next.js App Router.  Model data is embedded as RSC payloads
    via self.__next_f.push([1, "<json-encoded-string>"]).

    Each push payload is a JSON-encoded string.  When decoded, it contains
    newline-separated RSC rows like:
        5:["$","$L14",null,{"initialState":...,"children":["$","$L15",null,{"initialModels":[...]}]}]

    We scan pushes for the one containing 'rankByModality', decode it, and
    recursively search for the 'initialModels' array.
    """
    pushes = re.findall(r'self\.__next_f\.push\(\[1,(\".*?\")\]\)', html, re.DOTALL)

    def find_key(obj, key, depth=0):
        if depth > 12:
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

    for raw_push in pushes:
        try:
            decoded_str = json.loads(raw_push)
        except json.JSONDecodeError:
            continue

        if not isinstance(decoded_str, str):
            continue
        if "rankByModality" not in decoded_str:
            continue

        # RSC format: each line is "<hex_id>:<payload>"
        for line in decoded_str.splitlines():
            colon_idx = line.find(":")
            if colon_idx < 0:
                continue
            payload_str = line[colon_idx + 1:]
            if not payload_str or payload_str[0] not in "[{":
                continue
            try:
                obj = json.loads(payload_str)
            except json.JSONDecodeError:
                continue

            initial_models = find_key(obj, "initialModels")
            if not isinstance(initial_models, list) or not initial_models:
                continue

            rows = _rows_from_initial_models(initial_models)
            if rows:
                return rows

    return []


def _rows_from_initial_models(models: list) -> list[dict]:
    """
    Convert arena.ai initialModels list to our row format.

    Each model has:
      - displayName / publicName / name: model identifier
      - rank: overall arena rank (integer)
      - rankByModality.webdev: webdev-specific rank (integer)

    We use webdev rank when available, otherwise skip.
    Score = 1000 - rank so that rank 1 gets score 999, rank 2 gets 998, etc.
    (Inverted so higher score = better in our unified leaderboard.)
    """
    rows = []
    for item in models:
        if not isinstance(item, dict):
            continue

        modality_ranks = item.get("rankByModality", {})
        if not isinstance(modality_ranks, dict):
            continue

        webdev_rank = modality_ranks.get("webdev")
        if webdev_rank is None:
            continue

        # Skip sentinel values (JavaScript's MAX_SAFE_INTEGER = 9007199254740991
        # is used to indicate "unranked")
        try:
            webdev_rank_int = int(webdev_rank)
        except (TypeError, ValueError):
            continue
        if webdev_rank_int > 10000:
            continue

        name = (
            item.get("displayName")
            or item.get("publicName")
            or item.get("name")
        )
        if not name:
            continue

        # Invert rank to score: rank 1 → 999, rank 2 → 998, etc.
        score = 1000 - webdev_rank_int

        rows.append({
            "model": str(name),
            "benchmark": BENCHMARK_NAME,
            "score": float(score),
            "source": SOURCE,
        })

    return rows


def _rows_from_leaderboard_list(data: list) -> list[dict]:
    """
    Convert a list of leaderboard dicts (HF / API format) to our row format.
    Looks for Elo/rating fields and model name fields.
    """
    NAME_KEYS = ("model", "model_name", "name", "model_id", "modelName")
    ELO_KEYS = ("elo", "elo_rating", "rating", "score", "arena_score", "arena_elo",
                "webdev_elo", "webdev_score", "webdev_arena_elo")
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = next((item[k] for k in NAME_KEYS if k in item and item[k]), None)
        elo = next((_to_float(item[k]) for k in ELO_KEYS if k in item), None)
        if name and elo is not None:
            rows.append({
                "model": str(name),
                "benchmark": BENCHMARK_NAME,
                "score": elo,
                "source": SOURCE,
            })
    return rows


def _try_hf_dataset() -> list[dict]:
    """Try HuggingFace dataset viewer API."""
    for url in HF_DATASET_URLS:
        try:
            resp = requests.get(url, headers=JSON_HEADERS, timeout=TIMEOUT)
            if not resp.ok:
                continue
            data = resp.json()
            raw_rows = data.get("rows", [])
            items = [r.get("row", r) for r in raw_rows]
            rows = _rows_from_leaderboard_list(items)
            if rows:
                print(f"[{SOURCE}] Found {len(rows)} rows via HuggingFace dataset.", file=sys.stderr)
                return rows
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            pass
    return []


def _try_arena_api() -> list[dict]:
    """Try direct arena API endpoints."""
    for url in ARENA_API_URLS:
        try:
            resp = requests.get(url, headers=JSON_HEADERS, timeout=TIMEOUT)
            if not resp.ok or "json" not in resp.headers.get("content-type", ""):
                continue
            data = resp.json()
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = (
                    data.get("data")
                    or data.get("leaderboard")
                    or data.get("models")
                    or data.get("results")
                    or []
                )
            else:
                continue
            rows = _rows_from_leaderboard_list(items)
            if rows:
                print(f"[{SOURCE}] Found {len(rows)} rows via Arena API ({url}).", file=sys.stderr)
                return rows
        except (requests.RequestException, json.JSONDecodeError):
            pass
    return []


def _try_github_raw() -> list[dict]:
    """Try GitHub raw data files from lm-sys/arena-hard-auto."""
    for url in GITHUB_RAW_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if not resp.ok:
                continue
            data = resp.json()
            if isinstance(data, list):
                rows = _rows_from_leaderboard_list(data)
            elif isinstance(data, dict):
                items = (
                    data.get("data")
                    or data.get("leaderboard")
                    or data.get("models")
                    or []
                )
                rows = _rows_from_leaderboard_list(items)
            else:
                rows = []
            if rows:
                print(f"[{SOURCE}] Found {len(rows)} rows via GitHub raw ({url}).", file=sys.stderr)
                return rows
        except (requests.RequestException, json.JSONDecodeError):
            pass
    return []


def fetch() -> pd.DataFrame:
    rows: list[dict] = []

    # Strategy 1: arena.ai HTML (primary — has webdev-specific rank data)
    html = _fetch_arena_html()
    if html:
        rows = _extract_from_arena_html(html)
        if rows:
            print(f"[{SOURCE}] Found {len(rows)} rows via arena.ai HTML.", file=sys.stderr)

    # Strategy 2: HuggingFace dataset (Elo scores if available)
    if not rows:
        rows = _try_hf_dataset()

    # Strategy 3: Direct Arena API
    if not rows:
        rows = _try_arena_api()

    # Strategy 4: GitHub raw data
    if not rows:
        rows = _try_github_raw()

    if not rows:
        print(
            f"[{SOURCE}] WARNING: All automated extraction strategies failed.\n"
            f"  WebDev Arena data may require manual update.\n"
            f"  See: https://arena.ai/leaderboard",
            file=sys.stderr,
        )
        return EMPTY_DF

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["model", "benchmark"])
    df = df.sort_values("score", ascending=False).reset_index(drop=True)

    print(f"[{SOURCE}] Extracted {len(df)} WebDev Arena rows.", file=sys.stderr)
    return df


if __name__ == "__main__":
    df = fetch()
    if df.empty:
        print("No data returned — WebDev Arena may require manual update.")
        print("Visit: https://arena.ai/leaderboard")
    else:
        print(df.to_string(index=False))
