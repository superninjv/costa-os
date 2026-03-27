"""
benchmark-sources — Tier 1 benchmark data fetchers for Costa OS AI Router.

Each fetcher module downloads data from a specific leaderboard or benchmark
repository and returns a normalised pandas DataFrame with columns:

Required:
  model      (str)   — model name as reported by the source
  benchmark  (str)   — benchmark or category name
  score      (float) — primary metric (accuracy %, Elo, solve rate, etc.)
  source     (str)   — identifier of the data source

Optional (may be present in some fetchers):
  cost_input    (float) — cost per million input tokens (USD)
  cost_output   (float) — cost per million output tokens (USD)
  speed_tps     (float) — tokens per second (throughput)
  context_window (int) — maximum context window in tokens
  timestamp     (str)  — ISO 8601 date the score was recorded

Usage:
    from benchmark_sources import FETCHERS

    df = FETCHERS["bfcl"]()
    all_data = pd.concat([fn() for fn in FETCHERS.values()], ignore_index=True)

Each fetcher handles errors gracefully: on network failure it falls back to
local cache, and returns an empty DataFrame (with correct columns) as a last
resort — it never raises.
"""

from .epoch_ai import fetch_epoch_ai
from .bfcl import fetch_bfcl
from .livebench import fetch_livebench
from .swebench import fetch_swebench
from .llm2014 import fetch_llm2014
from .chatbot_arena import fetch_chatbot_arena
from .open_llm_leaderboard import fetch_open_llm_leaderboard

FETCHERS: dict = {
    "epoch_ai": fetch_epoch_ai,
    "bfcl": fetch_bfcl,
    "livebench": fetch_livebench,
    "swebench": fetch_swebench,
    "llm2014": fetch_llm2014,
    "chatbot_arena": fetch_chatbot_arena,
    "open_llm_leaderboard": fetch_open_llm_leaderboard,
}

__all__ = [
    "FETCHERS",
    "fetch_epoch_ai",
    "fetch_bfcl",
    "fetch_livebench",
    "fetch_swebench",
    "fetch_llm2014",
    "fetch_chatbot_arena",
    "fetch_open_llm_leaderboard",
]
