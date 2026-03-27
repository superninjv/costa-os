#!/usr/bin/env python3
"""Costa OS LLM Benchmark Aggregator — fetches from 12+ sources, cross-references, detects anomalies."""

import argparse
import importlib
import json
import pkgutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_SOURCES_DIR = Path(__file__).resolve().parent / "benchmark-sources"
ROUTER_OUTPUT = REPO_ROOT / "ai-router" / "benchmarks" / "consensus.json"
WEB_OUTPUT = REPO_ROOT / "ai-router" / "benchmarks" / "web-data.json"
PREVIOUS_RUN_PATH = REPO_ROOT / "ai-router" / "benchmarks" / "consensus.json"
ANOMALY_LOG = Path.home() / ".local" / "share" / "costa" / "benchmark-anomalies.json"

# ---------------------------------------------------------------------------
# Model alias mapping  (canonical → list of known aliases)
# ---------------------------------------------------------------------------

MODEL_ALIASES: dict[str, list[str]] = {
    # Anthropic Claude — every naming variant across sources
    "claude-opus-4.6": [
        "claude-opus-4.6", "claude opus 4.6", "Claude Opus 4.6",
        "claude-opus-4-6", "anthropic/claude-opus-4.6",
        "claude-opus-4-6-20250206",  # webdev_arena
    ],
    "claude-opus-4.5": [
        "claude-opus-4.5", "claude opus 4.5", "Claude Opus 4.5",
        "claude-opus-4-5", "anthropic/claude-opus-4.5",
        "Claude-Opus-4-5-20251101", "claude-opus-4-5-20251101",  # bfcl/webdev
        "Claude Opus 4.5",  # epoch_ai
    ],
    "claude-opus-4.1": [
        "claude-opus-4.1", "Claude Opus 4.1", "claude-opus-4-1",
        "claude-opus-4-1-20250805",  # webdev_arena
        "Claude Opus 4",  # epoch_ai
    ],
    "claude-sonnet-4.6": [
        "claude-sonnet-4.6", "claude sonnet 4.6", "Claude Sonnet 4.6",
        "claude-sonnet-4-6", "anthropic/claude-sonnet-4.6",
        "Claude Sonnet 4.6",  # vellum
    ],
    "claude-sonnet-4.5": [
        "claude-sonnet-4.5", "claude sonnet 4.5", "Claude Sonnet 4.5",
        "claude-sonnet-4-5", "anthropic/claude-sonnet-4.5",
        "Claude-Sonnet-4-5-20250929", "claude-sonnet-4-5-20250929",  # bfcl/webdev
    ],
    "claude-sonnet-4": [
        "claude-sonnet-4", "Claude Sonnet 4", "claude sonnet 4",
    ],
    "claude-haiku-4.5": [
        "claude-haiku-4.5", "claude haiku 4.5", "Claude Haiku 4.5",
        "claude-haiku-4-5", "anthropic/claude-haiku-4.5",
        "Claude-Haiku-4-5-20251001", "claude-haiku-4-5-20251001",  # bfcl/webdev
    ],
    "claude-3.5-sonnet": [
        "claude-3-5-sonnet-20240620", "Claude 3.5 Sonnet",
        "claude-3.5-sonnet", "Claude 3.5 Sonnet",
    ],
    "claude-3-opus": [
        "claude-3-opus-20240229", "Claude 3 Opus", "claude-3-opus",
    ],
    "claude-3-sonnet": [
        "claude-3-sonnet-20240229", "Claude 3 Sonnet", "claude-3-sonnet",
    ],
    "claude-3-haiku": [
        "claude-3-haiku-20240307", "Claude 3 Haiku", "claude-3-haiku",
    ],
    # OpenAI GPT
    "gpt-5.4": [
        "gpt-5.4", "GPT-5.4", "GPT 5.4", "openai/gpt-5.4", "gpt5.4",
    ],
    "gpt-5.3-codex": [
        "gpt-5.3-codex", "GPT-5.3 Codex", "GPT-5.3-Codex", "gpt-5.3 codex",
        "openai/gpt-5.3-codex", "codex-5.3",
    ],
    "gpt-5.2": [
        "gpt-5.2", "GPT-5.2", "openai/gpt-5.2", "gpt5.2",
    ],
    "gpt-5.1": [
        "gpt-5.1", "GPT-5.1", "openai/gpt-5.1", "gpt5.1",
    ],
    "gpt-5-mini": [
        "gpt-5-mini", "GPT-5 Mini", "gpt-5 mini", "openai/gpt-5-mini",
        "gpt5-mini",
    ],
    "gpt-5-nano": [
        "gpt-5-nano", "GPT-5 Nano", "gpt-5 nano", "openai/gpt-5-nano",
        "gpt5-nano",
    ],
    # Google Gemini
    "gemini-3.1-pro": [
        "gemini-3.1-pro", "Gemini 3.1 Pro", "gemini 3.1 pro",
        "google/gemini-3.1-pro", "gemini-3-1-pro",
    ],
    "gemini-3-pro": [
        "gemini-3-pro", "gemini-3.0-pro", "Gemini 3 Pro", "gemini 3 pro",
        "google/gemini-3-pro", "gemini 3.0 pro",
    ],
    "gemini-3-flash": [
        "gemini-3-flash", "gemini-3.0-flash", "Gemini 3 Flash",
        "gemini 3 flash", "google/gemini-3-flash", "gemini 3.0 flash",
    ],
    "gemini-3-flash-lite": [
        "gemini-3-flash-lite", "gemini-3.0-flash-lite", "Gemini 3 Flash Lite",
        "gemini 3 flash lite", "google/gemini-3-flash-lite",
    ],
    # Meta Llama
    "llama-4-scout": [
        "llama-4-scout", "Llama 4 Scout", "llama 4 scout",
        "meta/llama-4-scout", "meta-llama/llama-4-scout",
    ],
    "llama-4-maverick": [
        "llama-4-maverick", "Llama 4 Maverick", "llama 4 maverick",
        "meta/llama-4-maverick", "meta-llama/llama-4-maverick",
    ],
    "llama-3.1-405b": [
        "llama-3.1-405b", "Llama 3.1 405B", "llama 3.1 405b",
        "meta/llama-3.1-405b", "meta-llama/llama-3.1-405b-instruct",
        "llama-3.1-405b-instruct",
    ],
    "llama-3.1-70b": [
        "llama-3.1-70b", "Llama 3.1 70B", "llama 3.1 70b",
        "meta/llama-3.1-70b", "meta-llama/llama-3.1-70b-instruct",
        "llama-3.1-70b-instruct",
    ],
    "llama-3.1-8b": [
        "llama-3.1-8b", "Llama 3.1 8B", "llama 3.1 8b",
        "meta/llama-3.1-8b", "meta-llama/llama-3.1-8b-instruct",
        "llama-3.1-8b-instruct",
    ],
    # Alibaba Qwen
    "qwen-3.5-max": [
        "qwen-3.5-max", "Qwen3.5-Max", "qwen3.5 max", "qwen 3.5 max",
        "qwen/qwen-3.5-max", "qwen3.5-max",
    ],
    "qwen-3.5-plus": [
        "qwen-3.5-plus", "Qwen3.5-Plus", "qwen3.5 plus", "qwen 3.5 plus",
        "qwen/qwen-3.5-plus", "qwen3.5-plus",
    ],
    # Mistral
    "mistral-large-3": [
        "mistral-large-3", "Mistral Large 3", "mistral large 3",
        "mistralai/mistral-large-3", "mistral-large-latest",
    ],
    "devstral-small": [
        "devstral-small", "Devstral Small", "devstral small",
        "mistralai/devstral-small", "devstral",
    ],
    "codestral": [
        "codestral", "Codestral", "mistralai/codestral",
        "codestral-latest", "codestral-2501",
    ],
    "mistral-small": [
        "mistral-small", "Mistral Small", "Mistral-Small-2506",
        "mistralai/mistral-small", "mistral-small-latest",
    ],
    "mistral-nemo": [
        "mistral-nemo", "Mistral Nemo", "Mistral-Nemo",
        "mistralai/mistral-nemo", "mistral-nemo-latest",
    ],
    # OpenAI GPT-4.1 (still widely benchmarked)
    "gpt-4.1": [
        "gpt-4.1", "GPT-4.1", "GPT-4.1-2025-04-14",
        "gpt-4-1", "gpt4.1",
    ],
    "gpt-4.1-mini": [
        "gpt-4.1-mini", "GPT-4.1-mini", "GPT-4.1-mini-2025-04-14",
        "gpt-4-1-mini", "gpt4.1-mini",
    ],
    "gpt-4o": [
        "gpt-4o", "GPT-4o", "gpt-4o-2024-05-13", "gpt-4o-latest",
    ],
    "o3": ["o3", "OpenAI o3"],
    "o3-mini": ["o3-mini", "OpenAI o3-mini", "o3-mini-2025-01-31"],
    "gpt-oss-20b": [
        "gpt-oss-20b", "GPT oss 20b", "gpt-oss-120b",
    ],
    # Google Gemini 2.5 (still in many benchmarks)
    "gemini-2.5-pro": [
        "gemini-2.5-pro", "Gemini 2.5 Pro", "gemini-2-5-pro",
        "gemini-2.5-pro-preview", "gemini-1.5-pro-api-0514",
        "gemini-1.5-pro-api-0409-preview",
    ],
    "gemini-2.5-flash": [
        "gemini-2.5-flash", "Gemini 2.5 Flash", "gemini-2-5-flash",
        "gemini-2.5-flash-preview",
    ],
    "gemini-3.1-flash-lite": [
        "gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite",
        "gemini-3-1-flash-lite",
    ],
    # Meta Llama 3.3
    "llama-3.3-70b": [
        "llama-3.3-70b", "Llama 3.3 70B", "llama-3.3-70b-instruct",
        "Llama-3.3-70B-Instruct", "meta-llama/Llama-3.3-70B-Instruct",
        "Meta-Llama-3.3-70B-Instruct",
    ],
    # MiniMax
    "minimax-m2.5": [
        "minimax-m2.5", "MiniMax M2.5", "minimax m2.5",
        "minimax/m2.5", "MiniMax-M2.5",
    ],
    "minimax-m2.1": [
        "minimax-m2.1", "MiniMax M2.1", "MiniMax-M2.1",
    ],
    # DeepSeek
    "deepseek-v3.2": [
        "deepseek-v3.2", "DeepSeek-V3.2", "deepseek v3.2",
        "deepseek/deepseek-v3.2", "deepseek-v3-2",
        "DeepSeek V3.2-1201", "DeepSeek V3.2-Exp",
    ],
    "deepseek-r1": [
        "deepseek-r1", "DeepSeek-R1", "DeepSeek R1",
        "DeepSeek-R1-0528",
    ],
    # Grok
    "grok-4.1": [
        "grok-4.1", "Grok 4.1", "Grok 4.1 Fast",
    ],
    "grok-4.20": [
        "grok-4.20", "Grok 4.20 Beta", "Grok 4.20",
    ],
    # Kimi
    "kimi-k2.5": [
        "kimi-k2.5", "Kimi K2.5", "Kimi-K2.5",
    ],
}

# Reverse lookup: alias (lowercased, stripped) → canonical name
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in MODEL_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias.lower().strip()] = _canonical


# ---------------------------------------------------------------------------
# Benchmark categories
# ---------------------------------------------------------------------------

BENCHMARK_CATEGORIES: dict[str, list[str]] = {
    "coding": [
        # SWE-bench variants
        "SWE-bench Verified", "SWE-Bench Verified", "SWE-bench verified",
        "SWE-bench Lite", "SWE-bench Test", "SWE-bench Multilingual",
        "SWE-bench Multimodal", "SWE-bench Verified (bash-only)",
        # LiveBench coding
        "LiveBench/Coding", "LiveCodeBench",
        # Classic coding benchmarks
        "HumanEval", "MBPP",
        # llm2014 code categories
        "llm2014-code", "llm2014-code-v3",
        # Epoch AI
        "SWE-Bench verified",
    ],
    "reasoning": [
        # GPQA variants (different capitalizations across sources)
        "GPQA Diamond", "GPQA diamond", "GPQA",
        # Other reasoning
        "ARC-AGI 2", "Humanity's Last Exam",
        "llm2014-logic",
        # Epoch AI reasoning
        "SimpleQA Verified", "Chess Puzzles",
        # Scale AI
        "Scale AI Leaderboard Score",
        # LiveBench
        "LiveBench Average",
        # Open LLM Leaderboard
        "BBH", "MUSR",
    ],
    "math": [
        "AIME 2025", "MATH Level 5", "MATH-Hard", "MATH Lvl 5",
        "GSM8K",
        # Epoch AI math
        "OTIS Mock AIME 2024-2025",
        "FrontierMath-2025-02-28-Private", "FrontierMath-2025-02-28-Public",
        "FrontierMath-Tier-4-2025-07-01-Private", "FrontierMath-Tier-4-2025-07-01-Public",
    ],
    "tool_calling": [
        "BFCL Overall", "BFCL Live", "BFCL Non-Live", "BFCL Multi-Turn",
    ],
    "instruction_following": [
        "IFEval", "IFBench", "MultiChallenge",
        "LiveBench/Instruction Following",
    ],
    "frontend": [
        "WebDev Arena Elo", "WebDev Arena Rank",
    ],
    "general": [
        "MMLU-Pro", "MMLU-PRO", "MMMLU",
        "Arena Elo", "Chatbot Arena (Arena-Hard)",
        "Artificial Analysis Intelligence Index",
        "Open LLM Average",
        "LiveBench/Language",
    ],
    "long_context": [
        "RULER 128K", "MRCR v2",
    ],
    "vision": [
        "MMMU", "llm2014-vision",
    ],
    "speed": [
        "tokens_per_second",
    ],
    "cost": [
        "cost_per_1m_input", "cost_per_1m_output", "Pricing Data",
    ],
}

# Human-readable descriptions for web output
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "coding": "Code generation and software engineering benchmarks",
    "reasoning": "Complex reasoning, logic, and scientific knowledge",
    "math": "Mathematical problem solving from competition to graduate level",
    "tool_calling": "Function calling and API use accuracy",
    "instruction_following": "Adherence to complex, multi-constraint instructions",
    "frontend": "Web development capability via arena voting",
    "general": "Broad capability across diverse tasks",
    "long_context": "Retrieval and reasoning over long documents",
    "vision": "Multimodal visual understanding and analysis",
    "speed": "Inference throughput in tokens per second",
    "cost": "API pricing per million tokens",
}

# Reverse lookup: benchmark name (lowercased) → category
_BENCHMARK_TO_CATEGORY: dict[str, str] = {}
for _cat, _benchmarks in BENCHMARK_CATEGORIES.items():
    for _bench in _benchmarks:
        _BENCHMARK_TO_CATEGORY[_bench.lower()] = _cat


# Canonical benchmark names — map variants to a single name for deduplication
_BENCHMARK_CANONICAL: dict[str, str] = {}
for _cat, _benchmarks in BENCHMARK_CATEGORIES.items():
    # First entry in each list is the canonical name
    if _benchmarks:
        _canonical = _benchmarks[0]
        for _bench in _benchmarks:
            _BENCHMARK_CANONICAL[_bench.lower()] = _canonical


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def normalize_model_name(name: str) -> str:
    """Return canonical model name for any known alias.

    Handles case-insensitive matching, leading/trailing whitespace,
    and strips various suffixes: (Think), (high), (preview), (FC), (Prompt),
    thinking-Nk, date stamps like -20250929, etc.
    """
    import re
    if not name or not isinstance(name, str):
        return name

    original = name.strip()

    # Try exact match first (some aliases include suffixes intentionally)
    if original.lower() in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[original.lower()]

    # Progressive stripping — try each level of cleanup
    candidates = [original]

    # Strip parenthetical suffixes: (Think), (high), (FC), (Prompt), (preview), (no thinking)
    stripped_parens = re.sub(r"\s*\([^)]*\)\s*$", "", original).strip()
    if stripped_parens != original:
        candidates.append(stripped_parens)

    # Strip thinking/budget suffixes: -thinking-32k, -thinking, thinking
    stripped_thinking = re.sub(r"[-\s]*thinking[-\s]*\d*k?\s*$", "", stripped_parens, flags=re.IGNORECASE).strip()
    if stripped_thinking != stripped_parens:
        candidates.append(stripped_thinking)

    # Strip date stamps: -20250929, -20240620, etc.
    stripped_date = re.sub(r"[-_]\d{8,}$", "", stripped_thinking).strip()
    if stripped_date != stripped_thinking:
        candidates.append(stripped_date)

    # Strip epoch_ai style suffixes: " (Oct 2024)", " (Jun 2024)", " (16k thinking)"
    stripped_epoch = re.sub(r"\s*\([^)]*\d{4}[^)]*\)\s*$", "", original).strip()
    if stripped_epoch != original:
        candidates.append(stripped_epoch)
    stripped_epoch2 = re.sub(r"\s*\(\d+k thinking\)\s*$", "", original, flags=re.IGNORECASE).strip()
    if stripped_epoch2 != original:
        candidates.append(stripped_epoch2)
    stripped_epoch3 = re.sub(r"\s*\(no thinking\)\s*$", "", original, flags=re.IGNORECASE).strip()
    if stripped_epoch3 != original:
        candidates.append(stripped_epoch3)

    # Try all candidates
    for candidate in candidates:
        lookup = candidate.lower().strip()
        if lookup in _ALIAS_TO_CANONICAL:
            return _ALIAS_TO_CANONICAL[lookup]

    # Unknown model — return the most-stripped version
    return candidates[-1] if candidates else original


def normalize_model_names_in_df(df: pd.DataFrame) -> pd.DataFrame:
    """Apply normalize_model_name to the 'model' column of a DataFrame."""
    df = df.copy()
    df["model"] = df["model"].apply(normalize_model_name)
    return df


def expand_optional_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Generate synthetic benchmark rows from optional columns (speed_tps, cost_input, cost_output).

    Sources like artificial_analysis store speed and cost as columns on the same row
    as benchmark scores. This function creates additional rows so they can be categorized
    and ranked alongside other benchmarks.
    """
    extra_rows = []
    source = df["source"].iloc[0] if len(df) > 0 and "source" in df.columns else "unknown"

    if "speed_tps" in df.columns:
        speed_df = df[df["speed_tps"].notna()][["model", "speed_tps"]].drop_duplicates(subset=["model"])
        for _, row in speed_df.iterrows():
            extra_rows.append({
                "model": row["model"],
                "benchmark": "tokens_per_second",
                "score": float(row["speed_tps"]),
                "source": source,
            })

    if "cost_input" in df.columns:
        cost_df = df[df["cost_input"].notna()][["model", "cost_input"]].drop_duplicates(subset=["model"])
        for _, row in cost_df.iterrows():
            extra_rows.append({
                "model": row["model"],
                "benchmark": "cost_per_1m_input",
                "score": float(row["cost_input"]),
                "source": source,
            })

    if "cost_output" in df.columns:
        cost_df = df[df["cost_output"].notna()][["model", "cost_output"]].drop_duplicates(subset=["model"])
        for _, row in cost_df.iterrows():
            extra_rows.append({
                "model": row["model"],
                "benchmark": "cost_per_1m_output",
                "score": float(row["cost_output"]),
                "source": source,
            })

    if extra_rows:
        return pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)
    return df


# ---------------------------------------------------------------------------
# Score normalization
# ---------------------------------------------------------------------------

def normalize_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Min-max normalize scores to 0-100 scale per benchmark column.

    Expects a DataFrame where each column (other than 'model') represents
    a benchmark and values are raw scores.  Returns the same shape with
    scores scaled to [0, 100].
    """
    df = df.copy()
    score_cols = [c for c in df.columns if c != "model"]
    for col in score_cols:
        col_min = df[col].min()
        col_max = df[col].max()
        if col_max == col_min:
            df[col] = 50.0  # All identical — assign midpoint
        else:
            df[col] = (df[col] - col_min) / (col_max - col_min) * 100.0
    return df


# ---------------------------------------------------------------------------
# Consensus computation
# ---------------------------------------------------------------------------

def _pivot_long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot a long-form DataFrame (model, benchmark, score) to wide form."""
    return df.pivot_table(index="model", columns="benchmark", values="score", aggfunc="mean")


def compute_consensus(all_data: dict[str, pd.DataFrame]) -> dict:
    """Compute cross-source consensus rankings per category.

    Returns a dict keyed by category name. Each value is a dict with:
        "rankings": list of model dicts sorted by median_rank ascending.
    """
    # Collect per-benchmark scores across all sources, long format
    rows: list[dict] = []
    for source_name, df in all_data.items():
        for _, row in df.iterrows():
            rows.append({
                "model": row["model"],
                "benchmark": row.get("benchmark", "unknown"),
                "score": float(row["score"]) if pd.notna(row.get("score")) else np.nan,
                "source": source_name,
            })

    if not rows:
        return {cat: {"rankings": []} for cat in BENCHMARK_CATEGORIES}

    long_df = pd.DataFrame(rows)

    # Normalize benchmark names to canonical forms (case-insensitive dedup)
    long_df["benchmark_key"] = long_df["benchmark"].str.lower()
    long_df["category"] = long_df["benchmark_key"].map(_BENCHMARK_TO_CATEGORY).fillna("uncategorized")
    long_df["benchmark"] = long_df["benchmark_key"].map(_BENCHMARK_CANONICAL).fillna(long_df["benchmark"])

    consensus: dict[str, dict] = {}

    # Log uncategorized benchmarks for debugging
    uncategorized = long_df[long_df["category"] == "uncategorized"]["benchmark"].unique()
    if len(uncategorized) > 0:
        print(f"  [debug] Uncategorized benchmarks: {list(uncategorized)[:10]}", file=sys.stderr)

    for category, benchmarks in BENCHMARK_CATEGORIES.items():
        cat_df = long_df[long_df["category"] == category].copy()

        if cat_df.empty:
            consensus[category] = {"rankings": []}
            continue

        # For cost benchmarks, lower = better; for everything else, higher = better
        _LOWER_IS_BETTER = {"cost_per_1m_input", "cost_per_1m_output", "Pricing Data",
                            "cost_per_1m_input", "cost_per_1m_output"}

        # For each benchmark, rank models (rank 1 = best)
        model_ranks: dict[str, list[float]] = {}  # model → list of ranks across benchmarks
        model_scores: dict[str, dict[str, float]] = {}  # model → {benchmark: score}
        model_sources: dict[str, set[str]] = {}  # model → set of source names that contributed

        # Rank PER-SOURCE then merge — avoids sources with 4000+ entries
        # inflating ranks for models only appearing in smaller sources
        for source_name in cat_df["source"].unique():
            source_cat_df = cat_df[cat_df["source"] == source_name]

            for bench in source_cat_df["benchmark"].unique():
                bench_df = source_cat_df[source_cat_df["benchmark"] == bench][["model", "score"]].dropna(subset=["score"])
                if bench_df.empty:
                    continue

                # Rank within this source's entries for this benchmark
                ascending = bench in _LOWER_IS_BETTER
                bench_agg = bench_df.groupby("model")["score"].mean().reset_index()
                bench_agg = bench_agg.sort_values("score", ascending=ascending).reset_index(drop=True)
                total = len(bench_agg)
                # Normalize rank to percentile (0-100, lower = better) so different-sized
                # sources contribute equally
                bench_agg["pct_rank"] = (bench_agg.index / max(total - 1, 1)) * 100

                for _, r in bench_agg.iterrows():
                    model = r["model"]
                    model_sources.setdefault(model, set()).add(source_name)
                    if model not in model_ranks:
                        model_ranks[model] = []
                        model_scores[model] = {}
                    model_ranks[model].append(float(r["pct_rank"]))
                    # Keep the raw score (average if seen in multiple sources)
                    key = f"{bench} ({source_name})"
                    model_scores[model][key] = float(r["score"])

        if not model_ranks:
            consensus[category] = {"rankings": []}
            continue

        # Compute median rank, IQR, confidence, consensus_score per model
        rankings: list[dict] = []
        for model, ranks in model_ranks.items():
            ranks_arr = np.array(ranks)
            median_rank = float(np.median(ranks_arr))
            q75, q25 = np.percentile(ranks_arr, [75, 25])
            iqr = float(q75 - q25)

            if iqr < 2:
                confidence = "high"
            elif iqr <= 4:
                confidence = "medium"
            else:
                confidence = "low"

            # Consensus score: mean of normalised benchmark scores for this model/category
            raw_scores = list(model_scores[model].values())
            consensus_score = float(np.mean(raw_scores)) if raw_scores else 0.0

            num_sources = len(model_sources.get(model, set()))

            rankings.append({
                "model": model,
                "median_rank": median_rank,
                "consensus_score": round(consensus_score, 1),
                "sources": model_scores[model],
                "num_sources": num_sources,
                "iqr": round(iqr, 2),
                "confidence": confidence,
            })

        # Sort by: number of sources (desc, prefer cross-validated), then median rank, then score
        rankings.sort(key=lambda x: (-x["num_sources"], x["median_rank"], -x["consensus_score"]))
        # Keep top 50 to avoid 4000+ obscure fine-tunes from open_llm_leaderboard
        consensus[category] = {"rankings": rankings[:50]}

    return consensus


# ---------------------------------------------------------------------------
# Source health
# ---------------------------------------------------------------------------

def compute_source_health(all_data: dict[str, pd.DataFrame]) -> dict:
    """Compute pairwise Spearman rank correlations between sources.

    Returns a dict with:
        "correlations": {source_a: {source_b: rho}}
        "avg_correlation": {source: avg_rho_with_all_others}
        "flagged": [source names with avg < 0.6]
    """
    source_names = list(all_data.keys())
    n = len(source_names)
    corr_matrix: dict[str, dict[str, float]] = {s: {} for s in source_names}

    # Build per-source model→score mappings (average across benchmarks)
    source_avg: dict[str, pd.Series] = {}
    for name, df in all_data.items():
        if "score" in df.columns and "model" in df.columns:
            source_avg[name] = df.groupby("model")["score"].mean()

    for i in range(n):
        for j in range(i + 1, n):
            sa, sb = source_names[i], source_names[j]
            if sa not in source_avg or sb not in source_avg:
                continue
            # Align on common models
            common_models = source_avg[sa].index.intersection(source_avg[sb].index)
            if len(common_models) < 3:
                corr_matrix[sa][sb] = np.nan
                corr_matrix[sb][sa] = np.nan
                continue
            scores_a = source_avg[sa].loc[common_models].values
            scores_b = source_avg[sb].loc[common_models].values
            rho, _ = spearmanr(scores_a, scores_b)
            rho = float(rho) if not np.isnan(rho) else np.nan
            corr_matrix[sa][sb] = round(rho, 4) if not np.isnan(rho) else None
            corr_matrix[sb][sa] = round(rho, 4) if not np.isnan(rho) else None

    # Average correlation per source
    avg_corr: dict[str, float] = {}
    for source in source_names:
        peers = [v for v in corr_matrix[source].values() if v is not None]
        avg_corr[source] = round(float(np.mean(peers)), 4) if peers else 0.0

    flagged = [s for s, avg in avg_corr.items() if avg < 0.6]

    return {
        "correlations": corr_matrix,
        "avg_correlation": avg_corr,
        "flagged": flagged,
    }


# ---------------------------------------------------------------------------
# Pricing extraction
# ---------------------------------------------------------------------------

def extract_pricing(all_data: dict[str, pd.DataFrame]) -> dict:
    """Extract pricing data from sources that include cost columns.

    Returns a dict: {model: {cost_input, cost_output}} using the first
    non-null values found (prefer 'pricepertoken' or 'artificial_analysis' sources).
    """
    pricing: dict[str, dict] = {}

    # Prefer known authoritative pricing sources first
    preferred_order = ["pricepertoken", "artificial_analysis"] + [
        k for k in all_data if k not in ("pricepertoken", "artificial_analysis")
    ]

    for source_name in preferred_order:
        df = all_data.get(source_name)
        if df is None:
            continue
        cost_cols = [c for c in df.columns if c in ("cost_input", "cost_output")]
        if not cost_cols:
            continue
        for _, row in df.iterrows():
            model = row.get("model")
            if not model or model in pricing:
                continue
            entry: dict = {}
            if "cost_input" in row and pd.notna(row["cost_input"]):
                entry["cost_input"] = float(row["cost_input"])
            if "cost_output" in row and pd.notna(row["cost_output"]):
                entry["cost_output"] = float(row["cost_output"])
            if entry:
                pricing[model] = entry

    return pricing


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def detect_anomalies(current: dict, previous: dict) -> list[dict]:
    """Compare current and previous consensus dicts and return anomaly records.

    Anomaly types:
        - "rank_shift":  model moved >5 median ranks in a category
        - "source_divergence": per-source Spearman correlation vs previous run < 0.7
        - "stale_source": source present in previous but absent in current (or unchanged data)
    """
    anomalies: list[dict] = []

    current_cats = current.get("categories", current)
    previous_cats = previous.get("categories", previous)

    for category in BENCHMARK_CATEGORIES:
        curr_rankings = {
            r["model"]: r["median_rank"]
            for r in (current_cats.get(category, {}).get("rankings") or [])
        }
        prev_rankings = {
            r["model"]: r["median_rank"]
            for r in (previous_cats.get(category, {}).get("rankings") or [])
        }

        for model, curr_rank in curr_rankings.items():
            if model in prev_rankings:
                delta = abs(curr_rank - prev_rankings[model])
                if delta > 5:
                    anomalies.append({
                        "type": "rank_shift",
                        "severity": "high" if delta > 10 else "medium",
                        "category": category,
                        "model": model,
                        "previous_rank": prev_rankings[model],
                        "current_rank": curr_rank,
                        "delta": round(delta, 2),
                        "details": (
                            f"{model} moved {delta:.0f} places in {category}: "
                            f"rank {prev_rankings[model]:.0f} → {curr_rank:.0f}"
                        ),
                    })

    # Source-level correlation check (if previous has per-source data)
    prev_source_health = previous.get("source_health", {})
    prev_avg_corr = prev_source_health.get("avg_correlation", {})

    for source, prev_avg in prev_avg_corr.items():
        if isinstance(prev_avg, (int, float)) and prev_avg < 0.7:
            anomalies.append({
                "type": "source_divergence",
                "severity": "medium",
                "source": source,
                "previous_avg_correlation": prev_avg,
                "details": (
                    f"Source '{source}' had avg correlation {prev_avg:.3f} in previous run "
                    f"(threshold: 0.70)"
                ),
            })

    return anomalies


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _build_output_dict(
    consensus: dict,
    pricing: dict,
    health: dict,
    anomalies: list,
    sources_used: int,
    extra_meta: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    out: dict = {
        "generated": now,
        "sources_used": sources_used,
        "anomalies": anomalies,
        "categories": {},
        "pricing": pricing,
        "source_health": health,
    }
    if extra_meta:
        out.update(extra_meta)

    for category, data in consensus.items():
        out["categories"][category] = data

    return out


def output_router_json(
    consensus: dict,
    pricing: dict,
    health: dict,
    anomalies: list,
    sources_used: int = 0,
) -> None:
    """Write consensus data for the ai-router to consume."""
    ROUTER_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_output_dict(consensus, pricing, health, anomalies, sources_used)
    ROUTER_OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"Router consensus written → {ROUTER_OUTPUT}")


def output_web_json(
    consensus: dict,
    pricing: dict,
    health: dict,
    anomalies: list,
    sources_used: int = 0,
    source_metadata: dict | None = None,
) -> None:
    """Write enriched JSON for synoros.io visualization."""
    WEB_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    extra_meta = {
        "category_descriptions": CATEGORY_DESCRIPTIONS,
        "source_metadata": source_metadata or {},
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "benchmark_categories": BENCHMARK_CATEGORIES,
    }

    payload = _build_output_dict(
        consensus, pricing, health, anomalies, sources_used, extra_meta
    )
    WEB_OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"Web data written → {WEB_OUTPUT}")


# ---------------------------------------------------------------------------
# Previous-run loader
# ---------------------------------------------------------------------------

def load_previous_run() -> dict | None:
    """Load the previous consensus.json if it exists."""
    if PREVIOUS_RUN_PATH.exists():
        try:
            return json.loads(PREVIOUS_RUN_PATH.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: could not load previous run: {exc}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Anomaly notification
# ---------------------------------------------------------------------------

def notify_anomalies(anomalies: list[dict]) -> None:
    """Send a desktop notification and persist the anomaly log."""
    # Persist to log file
    ANOMALY_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if ANOMALY_LOG.exists():
        try:
            existing = json.loads(ANOMALY_LOG.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "anomalies": anomalies,
    }
    existing.append(entry)
    ANOMALY_LOG.write_text(json.dumps(existing, indent=2))

    # Desktop notification
    high_count = sum(1 for a in anomalies if a.get("severity") == "high")
    summary_line = f"{len(anomalies)} benchmark anomalies detected"
    if high_count:
        summary_line += f" ({high_count} high severity)"

    body_lines = []
    for a in anomalies[:5]:  # Show up to 5 in the notification body
        body_lines.append(a.get("details", str(a)))
    if len(anomalies) > 5:
        body_lines.append(f"… and {len(anomalies) - 5} more")

    try:
        subprocess.run(
            [
                "notify-send",
                "--urgency=normal",
                "--app-name=Costa OS Benchmarks",
                summary_line,
                "\n".join(body_lines),
            ],
            check=False,
        )
    except FileNotFoundError:
        pass  # notify-send not available


def write_anomaly_report(anomalies: list[dict]) -> None:
    """Write a standalone anomaly report JSON next to the consensus file."""
    report_path = ROUTER_OUTPUT.parent / "anomaly-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Anomaly report written → {report_path}")


# ---------------------------------------------------------------------------
# Fetcher discovery
# ---------------------------------------------------------------------------

def _ensure_sources_on_path() -> None:
    """Add benchmark-sources dir directly to sys.path for flat module imports.

    Because the directory name contains a hyphen it cannot be used as a Python
    package name.  We instead add the directory itself to sys.path so that each
    fetcher file (e.g. swebench.py) can be imported directly as `import swebench`.
    """
    sources_dir = str(BENCHMARK_SOURCES_DIR)
    if sources_dir not in sys.path:
        sys.path.insert(0, sources_dir)


def get_all_fetchers() -> list[tuple[str, object]]:
    """Discover all fetcher modules in benchmark-sources/ and return (name, callable) pairs.

    Each fetcher module must expose a top-level callable named `fetch()` that
    returns a pd.DataFrame with columns: model, benchmark, score, source.

    Private helper modules (names starting with '_') are skipped.
    """
    _ensure_sources_on_path()
    fetchers: list[tuple[str, object]] = []

    for finder, module_name, _ in pkgutil.iter_modules([str(BENCHMARK_SOURCES_DIR)]):
        if module_name.startswith("_"):
            continue  # Skip __init__, _cache, _nextjs, etc.
        try:
            module = importlib.import_module(module_name)
            # Try multiple naming conventions: fetch(), fetch_<name>(), FETCHER
            fetch_fn = None
            if hasattr(module, "fetch") and callable(module.fetch):
                fetch_fn = module.fetch
            elif hasattr(module, f"fetch_{module_name}") and callable(getattr(module, f"fetch_{module_name}")):
                fetch_fn = getattr(module, f"fetch_{module_name}")
            elif hasattr(module, "FETCHER") and callable(module.FETCHER):
                fetch_fn = module.FETCHER
            if fetch_fn:
                fetchers.append((module_name, fetch_fn))
        except ImportError as exc:
            print(f"Warning: could not import benchmark source '{module_name}': {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: error loading benchmark source '{module_name}': {exc}", file=sys.stderr)

    return fetchers


def get_fetchers(
    requested: str | None = None,
) -> list[tuple[str, object]]:
    """Return fetchers filtered by comma-separated source names (or all if None)."""
    all_fetchers = get_all_fetchers()
    if not requested:
        return all_fetchers

    wanted = {s.strip().lower() for s in requested.split(",")}
    return [(name, fn) for name, fn in all_fetchers if name.lower() in wanted]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Costa OS LLM Benchmark Aggregator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run, write router + web output, compare with previous
  benchmark-aggregator.py --output-router --output-web --compare-previous

  # Dry run with verbose output from specific sources
  benchmark-aggregator.py --dry-run --verbose --sources swebench,livebench

  # Update only web data
  benchmark-aggregator.py --output-web
""",
    )
    parser.add_argument(
        "--output-router",
        action="store_true",
        help=f"Write consensus data to {ROUTER_OUTPUT}",
    )
    parser.add_argument(
        "--output-web",
        action="store_true",
        help=f"Write web visualization data to {WEB_OUTPUT}",
    )
    parser.add_argument(
        "--compare-previous",
        action="store_true",
        help="Load previous run and run anomaly detection",
    )
    parser.add_argument(
        "--sources",
        metavar="SOURCE1,SOURCE2",
        default=None,
        help="Comma-separated list of source module names to use (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and analyze but do not write any output files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-source fetch progress and detailed stats",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # ------------------------------------------------------------------
    # 1. Import and run fetchers
    # ------------------------------------------------------------------
    all_data: dict[str, pd.DataFrame] = {}
    fetcher_list = get_fetchers(args.sources)
    all_fetcher_count = len(get_all_fetchers())

    if not fetcher_list:
        print("No fetcher modules found in benchmark-sources/.", file=sys.stderr)
        print(
            "Add fetcher modules (each exposing a fetch() function) to "
            f"{BENCHMARK_SOURCES_DIR}",
            file=sys.stderr,
        )

    for source_name, fetcher in fetcher_list:
        try:
            df = fetcher()
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"fetch() must return a DataFrame, got {type(df).__name__}")
            all_data[source_name] = df
            if args.verbose:
                print(f"✓ {source_name}: {len(df)} rows")
        except Exception as exc:
            print(f"✗ {source_name}: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 2. Normalize model names, expand optional columns, check freshness
    # ------------------------------------------------------------------
    # Current-generation models — if a source has none of these, it's stale
    CURRENT_MODELS = {
        "claude-opus-4.6", "claude-sonnet-4.6", "gpt-5.2", "gpt-5.4",
        "gemini-3-pro", "gemini-3.1-pro", "gemini-3-flash",
    }
    stale_sources = set()

    for name, df in all_data.items():
        df = normalize_model_names_in_df(df)
        df = expand_optional_columns(df)
        all_data[name] = df

        # Check if source has any current-generation models
        if len(df) > 0:
            source_models = set(df["model"].unique())
            has_current = bool(source_models & CURRENT_MODELS)
            if not has_current and name not in ("pricepertoken", "open_llm_leaderboard"):
                stale_sources.add(name)
                if args.verbose:
                    print(f"  ⚠ {name}: STALE — no current-generation models found")

    # Remove stale sources from consensus computation (still keep for reference)
    for stale in stale_sources:
        if args.verbose:
            print(f"  Excluding stale source '{stale}' from consensus")
        del all_data[stale]

    # ------------------------------------------------------------------
    # 3. Compute consensus, health, pricing
    # ------------------------------------------------------------------
    consensus = compute_consensus(all_data)
    health = compute_source_health(all_data)
    pricing = extract_pricing(all_data)

    if args.verbose:
        print(f"\nSource health:")
        for source, avg in health.get("avg_correlation", {}).items():
            flag = " [FLAGGED]" if source in health.get("flagged", []) else ""
            print(f"  {source}: avg_corr={avg:.3f}{flag}")

    # ------------------------------------------------------------------
    # 4. Anomaly detection
    # ------------------------------------------------------------------
    anomalies: list[dict] = []
    if args.compare_previous:
        previous = load_previous_run()
        if previous:
            anomalies = detect_anomalies(consensus, previous)
            if anomalies:
                notify_anomalies(anomalies)
                print(f"\n⚠  {len(anomalies)} anomalies detected:")
                for a in anomalies:
                    sev = a.get("severity", "?").upper()
                    print(f"  [{sev}] {a.get('details', a)}")

                if not args.dry_run:
                    print("Router consensus data NOT updated due to anomalies.")
                    write_anomaly_report(anomalies)
                    # Still write web data so the site reflects the situation
                    if args.output_web:
                        output_web_json(
                            consensus, pricing, health, anomalies,
                            sources_used=len(all_data),
                        )
                    return
        else:
            if args.verbose:
                print("No previous run found — skipping anomaly comparison.")

    # ------------------------------------------------------------------
    # 5. Write outputs
    # ------------------------------------------------------------------
    if not args.dry_run:
        if args.output_router:
            output_router_json(
                consensus, pricing, health, anomalies,
                sources_used=len(all_data),
            )
        if args.output_web:
            output_web_json(
                consensus, pricing, health, anomalies,
                sources_used=len(all_data),
            )

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print(f"\nSources: {len(all_data)}/{all_fetcher_count}")
    if args.verbose:
        for source in all_data:
            print(f"  ✓ {source}")

    for cat, data in consensus.items():
        rankings = data.get("rankings", [])
        if rankings:
            top = rankings[0]
            print(
                f"  {cat:22s}: #1 {top['model']} "
                f"(score: {top['consensus_score']:.1f}, "
                f"conf: {top['confidence']})"
            )
        else:
            print(f"  {cat:22s}: no data")

    if args.dry_run:
        print("\n[dry-run] No files written.")


if __name__ == "__main__":
    main()
