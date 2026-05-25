"""Calls Claude Sonnet to synthesize the digest markdown. See SPEC §9.3."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


async def synthesize_digest(items: list[dict[str, Any]]) -> str:
    """Return the digest body in Markdown."""
    prompt_template = Path("/root/src/prompts/digest.md").read_text()
    prompt = prompt_template.format(
        items_json=json.dumps(items, default=str, indent=2)
    )

    client = _get_client()
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if hasattr(block, "text"))
