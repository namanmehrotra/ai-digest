"""Top-level ingestion orchestrator. See SPEC §9.1.

Reads sources.yaml, fetches each source, deduplicates, tags, embeds, and stores.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


async def run_ingest() -> None:
    """Top-level ingestion run, called by the Modal cron.

    Phase 1 flow (TODO — implement):
      1. Load sources.yaml.
      2. For each source:
         a. If type=rss, parse with feedparser.
         b. If type=html, fetch listing with httpx and parse item URLs.
      3. For each item URL:
         a. Fetch full page with httpx.
         b. Run trafilatura.extract() to get clean text + metadata.
         c. Skip if URL or content_hash already in articles.
         d. Tag via Claude Haiku (src.ingest.tagger.tag).
         e. Embed via Voyage (src.ingest.embedder.embed).
         f. Compute signal_score (src.scoring.compute_signal_score).
         g. INSERT into articles.
      4. Log per-source counts; raise on >5 consecutive failures for a source.
    """
    sources_path = Path("/root/sources.yaml")
    sources = yaml.safe_load(sources_path.read_text())
    logger.info("Loaded %d source buckets", len(sources))

    raise NotImplementedError("Implement in Phase 1")
