"""Selects articles for the next digest. See SPEC §9.3.

Pulls signal-ranked candidates from articles, applies per-bucket caps,
fills remaining slots up to the total cap.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.db import conn

BUCKET_ORDER = ["frontier_labs", "practitioners", "papers", "industry"]
PER_BUCKET_CAP = 3
TOTAL_CAP = 12


async def select_for_digest(*, since: datetime) -> list[dict[str, Any]]:
    """Return up to TOTAL_CAP articles, signal-ranked, with per-bucket caps."""
    async with conn() as c:
        rows = await c.fetch(
            """
            SELECT id, url, source_name, source_bucket, title, summary,
                   why_it_matters, topics, signal_score, published_at
            FROM articles
            WHERE ingested_at > $1
            ORDER BY signal_score DESC
            LIMIT 60
            """,
            since,
        )

    by_bucket: dict[str, list[dict]] = {b: [] for b in BUCKET_ORDER}
    leftovers: list[dict] = []
    for row in rows:
        item = dict(row)
        bucket = item["source_bucket"]
        if bucket in by_bucket and len(by_bucket[bucket]) < PER_BUCKET_CAP:
            by_bucket[bucket].append(item)
        else:
            leftovers.append(item)

    selected: list[dict] = [item for b in BUCKET_ORDER for item in by_bucket[b]]
    remaining = TOTAL_CAP - len(selected)
    if remaining > 0:
        selected.extend(leftovers[:remaining])

    return selected[:TOTAL_CAP]
