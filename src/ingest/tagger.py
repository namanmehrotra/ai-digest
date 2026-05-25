"""Tagging via Claude Haiku — generates summary, why_it_matters, topics, vega_relevance."""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


async def tag(*, title: str, source_name: str, author: str, raw_text: str) -> dict:
    """Return dict with keys: summary, why_it_matters, topics, vega_relevance.

    Truncates raw_text to ~12k chars to keep tagging cheap.
    """
    prompt_template = Path("/root/src/prompts/tagging.md").read_text()
    prompt = prompt_template.format(
        title=title,
        source_name=source_name,
        author=author,
        raw_text=raw_text[:12000],
    )
    client = _get_client()
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in msg.content if hasattr(block, "text"))
    return json.loads(text)
