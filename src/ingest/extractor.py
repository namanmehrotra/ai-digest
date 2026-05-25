"""Article content extraction using trafilatura."""

from __future__ import annotations

import json

import trafilatura


def extract(html: str, url: str | None = None) -> tuple[str, dict[str, str]] | None:
    """Extract clean article text + metadata from HTML.

    Returns (text, metadata) or None if no substantive content found.
    Metadata keys: title, author, date, sitename.
    """
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
        with_metadata=True,
        output_format="json",
    )
    if not extracted:
        return None

    obj = json.loads(extracted)
    text = obj.get("text") or ""
    if len(text) < 200:
        return None  # Too short to be a useful article

    return text, {
        "title": obj.get("title", "") or "",
        "author": obj.get("author", "") or "",
        "date": obj.get("date", "") or "",
        "sitename": obj.get("sitename", "") or "",
    }
