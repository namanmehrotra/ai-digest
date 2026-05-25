"""Signal scoring for articles. See SPEC §9.2.

signal_score in [0, 1] =
    0.35 * cross_source_count_norm
  + 0.25 * source_authority_weight
  + 0.20 * recency_decay
  + 0.10 * keyword_boost
  + 0.10 * vega_relevance_boost
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Per-source authority weights. Tune over time.
SOURCE_AUTHORITY: dict[str, float] = {
    "Anthropic News": 1.0,
    "OpenAI Blog": 1.0,
    "Google DeepMind Blog": 1.0,
    "Meta AI": 0.9,
    "Mistral News": 0.85,
    "AI2 Blog": 0.85,
    "xAI News": 0.85,
    "Simon Willison": 0.95,
    "One Useful Thing (Ethan Mollick)": 0.9,
    "Interconnects (Nathan Lambert)": 0.95,
    "Latent Space (Swyx)": 0.9,
    "Eugene Yan": 0.85,
    "Hamel Husain": 0.85,
    "Jason Liu": 0.8,
    "Sebastian Raschka — Ahead of AI": 0.9,
    "Lilian Weng": 0.9,
    "HuggingFace Daily Papers": 0.85,
    "arxiv-sanity top": 0.7,
    "AlphaSignal": 0.7,
    "TechCrunch AI": 0.5,
    "The Verge AI": 0.5,
    "HackerNews — AI-filtered top": 0.75,
    "GitHub trending — Python AI": 0.7,
}

DEFAULT_AUTHORITY = 0.6

KEYWORD_BOOST_TERMS = {
    "claude", "gpt", "gemini", "llama", "release", "launch", "introducing",
    "paper", "ablation", "benchmark", "sota", "anthropic", "openai", "deepmind",
}

VEGA_BOOSTS = {"general": 0.3, "claims": 0.9, "agent-building": 0.9, "high": 1.0}


def compute_signal_score(
    *,
    cross_source_count: int,
    source_name: str,
    published_at: datetime,
    title: str,
    vega_relevance: str,
) -> float:
    """Compute 0..1 signal score for an article. See SPEC §9.2."""
    cross_norm = min(cross_source_count / 3.0, 1.0)
    authority = SOURCE_AUTHORITY.get(source_name, DEFAULT_AUTHORITY)

    age_hours = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600
    recency = math.exp(-max(age_hours, 0) / 72.0)

    title_lower = title.lower()
    keyword = 1.0 if any(t in title_lower for t in KEYWORD_BOOST_TERMS) else 0.3

    vega = VEGA_BOOSTS.get(vega_relevance, 0.3)

    return (
        0.35 * cross_norm
        + 0.25 * authority
        + 0.20 * recency
        + 0.10 * keyword
        + 0.10 * vega
    )
