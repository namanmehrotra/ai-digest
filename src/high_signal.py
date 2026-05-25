"""High-signal interrupt monitor. See SPEC §9.4.

Phase 2 implementation.

Flow:
  1. Query articles ingested in last 12h with signal_score > 0.75 OR cross_source_count >= 4.
  2. Check high_signal_state.last_fired_at — if within last 24h, skip (cooldown).
  3. Synthesize short interrupt email (1-3 items, ~150 words) via Claude Sonnet.
  4. Send via Resend.
  5. Update high_signal_state.last_fired_at.

Bias toward false negatives — better to miss an interrupt than over-fire.
"""

from __future__ import annotations


async def check_and_fire() -> None:
    """Entry point called by Modal cron."""
    raise NotImplementedError("Implement in Phase 2")
