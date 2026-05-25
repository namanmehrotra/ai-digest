"""Sends the digest email via Resend, then logs to the digests table.

See SPEC §9.3.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import markdown as md
import resend

from src.db import conn
from src.digest.selector import select_for_digest
from src.digest.synthesizer import synthesize_digest


async def send_scheduled_digest() -> None:
    """Compose and send the Tue/Fri digest."""
    async with conn() as c:
        last_sent = await c.fetchval(
            "SELECT sent_at FROM digests WHERE kind = 'scheduled' "
            "ORDER BY sent_at DESC LIMIT 1"
        )

    since = last_sent or datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = await select_for_digest(since=since)
    if not items:
        return  # Quiet cycle, send nothing

    body_md = await synthesize_digest(items)
    body_html = md.markdown(body_md, extensions=["extra"])

    resend.api_key = os.environ["RESEND_API_KEY"]
    today = datetime.now(timezone.utc).strftime("%a %b %-d")
    subject = f"AI Digest — {today}"

    result = resend.Emails.send(
        {
            "from": os.environ["DIGEST_FROM_EMAIL"],
            "to": [os.environ["DIGEST_RECIPIENT_EMAIL"]],
            "subject": subject,
            "html": body_html,
            "text": body_md,
        }
    )

    async with conn() as c:
        await c.execute(
            """
            INSERT INTO digests (kind, subject, body_md, body_html, article_ids, resend_message_id)
            VALUES ('scheduled', $1, $2, $3, $4, $5)
            """,
            subject,
            body_md,
            body_html,
            [item["id"] for item in items],
            result.get("id"),
        )
