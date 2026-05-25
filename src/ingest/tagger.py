"""Tagging via Claude Haiku — generates summary, why_it_matters, topics, vega_relevance."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _extract_json(raw: str) -> dict:
    """Parse JSON from Claude's response, handling code-fence wrapping.

    Claude Haiku often wraps JSON in ```json ... ``` even when told not to.
    Strategy: strip fences, then fall back to finding the first { ... } span.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Last resort: find outermost { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in tagger response. Raw: {raw[:300]!r}")


async def tag(*, title: str, source_name: str, author: str, raw_text: str) -> dict:
    """Return dict with keys: summary, why_it_matters, topics, vega_relevance.

    Truncates raw_text to ~12k chars to keep tagging cheap.
    """
    prompt_template = Path("/root/src/prompts/tagging.md").read_text()
    # Use format_map with a safe mapping so stray {} in raw_text don't blow up
    prompt = prompt_template.format(
        title=title,
        source_name=source_name,
        author=author,
        raw_text=raw_text[:12000],
    )
    client = _get_client()
    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in msg.content if hasattr(block, "text"))
    return _extract_json(text)
