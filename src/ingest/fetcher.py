"""Top-level ingestion orchestrator. See SPEC §9.1.

Reads sources.yaml, fetches each source, deduplicates, tags, embeds, and stores.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import httpx
import yaml
from dateutil.parser import parse as dateutil_parse
from lxml import html as lxml_html

from src.db import conn
from src.ingest.embedder import embed_document
from src.ingest.extractor import extract
from src.ingest.tagger import tag as tag_article
from src.scoring import compute_signal_score

logger = logging.getLogger(__name__)

USER_AGENT = "ai-digest-personal/1.0 (+github.com/namanmehrotra/ai-digest)"
MAX_CONCURRENCY = 8
FETCH_TIMEOUT = 30.0
MAX_ITEMS_PER_SOURCE = 20
VALID_VEGA_RELEVANCE = {"general", "claims", "agent-building", "high"}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class FeedItem:
    """Minimal descriptor for one ingestion candidate."""

    url: str
    title: str = ""
    author: str = ""
    published_at: datetime | None = None
    feed_text: str = field(default="", repr=False)


# ---------------------------------------------------------------------------
# HTML listing parsers
# Each function takes (html: str, base_url: str) -> list[str] of article URLs.
# ---------------------------------------------------------------------------


def _extract_links(
    html_content: str,
    base_url: str,
    predicate: Callable[[str], bool],
) -> list[str]:
    """Extract deduplicated absolute URLs matching predicate from an HTML page."""
    try:
        tree = lxml_html.fromstring(html_content.encode())
        tree.make_links_absolute(base_url)
    except Exception as exc:
        logger.debug("HTML parse error for %s: %s", base_url, exc)
        return []

    seen: set[str] = set()
    result: list[str] = []
    for element, attr, link, _ in tree.iterlinks():
        if element.tag != "a" or attr != "href":
            continue
        parsed = urlparse(link)
        # Normalise: strip query string + fragment + trailing slash
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        if not clean or clean in seen:
            continue
        if predicate(clean):
            seen.add(clean)
            result.append(clean)

    return result


def _parse_anthropic(html: str, base_url: str) -> list[str]:
    """https://www.anthropic.com/news/<slug>"""
    return _extract_links(
        html,
        base_url,
        lambda url: (
            "anthropic.com/news/" in url
            and url.rstrip("/") != "https://www.anthropic.com/news"
        ),
    )


def _parse_deepmind(html: str, base_url: str) -> list[str]:
    """https://deepmind.google/discover/blog/<slug>/"""
    return _extract_links(
        html,
        base_url,
        lambda url: (
            "deepmind.google" in url
            and "/discover/blog/" in url
            and url.rstrip("/") != "https://deepmind.google/discover/blog"
        ),
    )


def _parse_meta_ai(html: str, base_url: str) -> list[str]:
    """https://ai.meta.com/blog/<slug>/"""
    return _extract_links(
        html,
        base_url,
        lambda url: (
            "ai.meta.com/blog/" in url
            and url.rstrip("/") != "https://ai.meta.com/blog"
        ),
    )


def _parse_mistral(html: str, base_url: str) -> list[str]:
    """https://mistral.ai/news/<slug>/"""
    return _extract_links(
        html,
        base_url,
        lambda url: (
            "mistral.ai/news/" in url
            and url.rstrip("/") != "https://mistral.ai/news"
        ),
    )


def _parse_ai2(html: str, base_url: str) -> list[str]:
    """https://allenai.org/blog/<slug>"""
    return _extract_links(
        html,
        base_url,
        lambda url: (
            "allenai.org/blog/" in url
            and url.rstrip("/") != "https://allenai.org/blog"
        ),
    )


def _parse_xai(html: str, base_url: str) -> list[str]:
    """https://x.ai/news/<slug> — site may be JS-rendered; returns empty if so."""
    return _extract_links(
        html,
        base_url,
        lambda url: (
            "x.ai/news/" in url
            and url.rstrip("/") != "https://x.ai/news"
        ),
    )


def _parse_hf_papers(html: str, base_url: str) -> list[str]:
    """https://huggingface.co/papers/<arxiv_id>"""
    return _extract_links(
        html,
        base_url,
        lambda url: (
            "huggingface.co/papers/" in url
            and url.rstrip("/") != "https://huggingface.co/papers"
        ),
    )


def _parse_arxiv_sanity(html: str, base_url: str) -> list[str]:
    """arxiv-sanity-lite — extracts arxiv.org/abs/ links."""
    return _extract_links(
        html,
        base_url,
        lambda url: "arxiv.org/abs/" in url,
    )


def _parse_alphasignal(html: str, base_url: str) -> list[str]:
    """AlphaSignal — newsletter aggregator; site may be JS-rendered."""
    # Try a few known URL patterns for AlphaSignal article links
    for pattern in ("/post/", "/article/", "/issue/"):
        results = _extract_links(
            html,
            base_url,
            lambda url, p=pattern: "alphasignal.ai" in url and p in url,
        )
        if results:
            return results
    return []


def _parse_github_trending(html: str, base_url: str) -> list[str]:
    """GitHub trending repos — links like https://github.com/<user>/<repo>."""

    def _is_repo_link(url: str) -> bool:
        parsed = urlparse(url)
        if "github.com" not in parsed.netloc:
            return False
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        return (
            len(parts) == 2
            and parts[0] not in {"trending", "features", "topics", "explore"}
        )

    return _extract_links(html, base_url, _is_repo_link)


_HTML_PARSERS: dict[str, Callable[[str, str], list[str]]] = {
    "Anthropic News": _parse_anthropic,
    "Google DeepMind Blog": _parse_deepmind,
    "Meta AI": _parse_meta_ai,
    "Mistral News": _parse_mistral,
    "AI2 Blog": _parse_ai2,
    "xAI News": _parse_xai,
    "HuggingFace Daily Papers": _parse_hf_papers,
    "arxiv-sanity top": _parse_arxiv_sanity,
    "AlphaSignal": _parse_alphasignal,
    "GitHub trending — Python AI": _parse_github_trending,
}


# ---------------------------------------------------------------------------
# Polite HTTP fetching
# ---------------------------------------------------------------------------


async def _polite_get(
    client: httpx.AsyncClient,
    url: str,
    sem: asyncio.Semaphore,
    host_last: dict[str, float],
) -> httpx.Response:
    """Rate-limited, jittered GET. Enforces 1s minimum gap per host."""
    host = urlparse(url).netloc
    async with sem:
        now = time.monotonic()
        last = host_last.get(host, 0.0)
        gap = last + 1.0 - now
        if gap > 0:
            await asyncio.sleep(gap)
        # Jitter on top of the minimum gap
        await asyncio.sleep(random.uniform(0.0, 0.5))
        host_last[host] = time.monotonic()
        return await client.get(url, timeout=FETCH_TIMEOUT)


# ---------------------------------------------------------------------------
# Source-level fetching
# ---------------------------------------------------------------------------


async def _get_rss_items(
    url: str,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    host_last: dict[str, float],
) -> list[FeedItem]:
    """Fetch an RSS/Atom feed and return FeedItems."""
    try:
        resp = await _polite_get(client, url, sem, host_last)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("RSS fetch failed %s: %s", url, exc)
        return []

    loop = asyncio.get_running_loop()
    feed = await loop.run_in_executor(None, feedparser.parse, resp.content)

    items: list[FeedItem] = []
    for entry in feed.entries:
        link = entry.get("link", "").strip()
        if not link:
            continue

        pub: datetime | None = None
        for attr in ("published_parsed", "updated_parsed"):
            val = entry.get(attr)
            if val:
                pub = datetime.fromtimestamp(calendar.timegm(val), tz=UTC)
                break

        feed_text = ""
        if entry.get("content"):
            feed_text = entry.content[0].get("value", "")
        elif entry.get("summary"):
            feed_text = entry.summary or ""

        items.append(
            FeedItem(
                url=link,
                title=entry.get("title", ""),
                author=entry.get("author", ""),
                published_at=pub,
                feed_text=feed_text,
            )
        )

    return items


async def _get_html_items(
    source: dict,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    host_last: dict[str, float],
) -> list[FeedItem]:
    """Fetch an HTML listing page and extract candidate article URLs."""
    url = source["url"]
    name = source["name"]

    parser_fn = _HTML_PARSERS.get(name)
    if parser_fn is None:
        logger.warning("No HTML parser registered for %r — skipping", name)
        return []

    try:
        resp = await _polite_get(client, url, sem, host_last)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Listing fetch failed %s: %s", url, exc)
        return []

    urls = parser_fn(resp.text, str(resp.url))
    logger.debug("%s: found %d candidate URLs in listing", name, len(urls))
    return [FeedItem(url=u) for u in urls]


# ---------------------------------------------------------------------------
# Cross-source count (used for signal scoring)
# ---------------------------------------------------------------------------


async def _cross_source_count(title: str) -> int:
    """Count distinct sources that mentioned a similar title in the last 7 days."""
    words = [w.lower() for w in title.split() if len(w) >= 5][:5]
    if not words:
        return 0
    patterns = [f"%{w}%" for w in words]
    async with conn() as c:
        count = await c.fetchval(
            """
            SELECT COUNT(DISTINCT source_name)
            FROM articles
            WHERE ingested_at > NOW() - INTERVAL '7 days'
              AND title ILIKE ANY($1::text[])
            """,
            patterns,
        )
    return int(count or 0)


# ---------------------------------------------------------------------------
# Per-item processing
# ---------------------------------------------------------------------------


async def _process_item(
    item: FeedItem,
    source_name: str,
    bucket: str,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    host_last: dict[str, float],
) -> bool:
    """Fetch, extract, dedup, tag, embed, score, and insert one article.

    Returns True if a new article was inserted.
    """
    # 1. Fetch full article HTML
    try:
        resp = await _polite_get(client, item.url, sem, host_last)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        logger.debug("Fetch failed %s: %s", item.url, exc)
        return False

    # 2. Extract clean text + metadata
    extracted = extract(html, url=item.url)
    if extracted is None:
        if len(item.feed_text) >= 200:
            raw_text = item.feed_text
            meta: dict[str, str] = {
                "title": item.title,
                "author": item.author,
                "date": "",
                "sitename": "",
            }
        else:
            logger.debug("No extractable content at %s", item.url)
            return False
    else:
        raw_text, meta = extracted

    # Prefer RSS-provided title/author over trafilatura's
    title = item.title or meta.get("title", "") or item.url
    author = item.author or meta.get("author", "")

    # 3. Content hash for dedup
    content_hash = hashlib.sha256(raw_text.strip().encode()).hexdigest()

    # 4. Dedup check (URL or identical content already stored)
    async with conn() as c:
        exists = await c.fetchval(
            "SELECT 1 FROM articles WHERE url = $1 OR content_hash = $2 LIMIT 1",
            item.url,
            content_hash,
        )
    if exists:
        return False

    # 5. Resolve published_at
    published_at = item.published_at
    if published_at is None and meta.get("date"):
        try:
            published_at = dateutil_parse(meta["date"]).replace(tzinfo=UTC)
        except Exception:
            pass
    if published_at is None:
        published_at = datetime.now(UTC)

    # 6. Tag via Claude Haiku
    try:
        tag_result = await tag_article(
            title=title,
            source_name=source_name,
            author=author,
            raw_text=raw_text,
        )
    except Exception as exc:
        logger.warning("Tagging failed for %s: %s", item.url, exc)
        return False

    vega = tag_result.get("vega_relevance", "general")
    if vega not in VALID_VEGA_RELEVANCE:
        vega = "general"

    # 7. Embed via Voyage (failure is logged but does not block insert)
    embedding: list[float] | None = None
    try:
        embed_input = f"{title}\n\n{tag_result.get('summary', '')}\n\n{raw_text[:8000]}"
        embedding = await embed_document(embed_input)
    except Exception as exc:
        logger.warning("Embedding failed for %s: %s", item.url, exc)

    # 8. Signal score
    cross_count = await _cross_source_count(title)
    signal_score = compute_signal_score(
        cross_source_count=cross_count,
        source_name=source_name,
        published_at=published_at,
        title=title,
        vega_relevance=vega,
    )

    # 9. Insert (ON CONFLICT handles any race with a concurrent ingest run)
    async with conn() as c:
        await c.execute(
            """
            INSERT INTO articles (
                url, source_name, source_bucket, title, author, published_at,
                raw_text, summary, why_it_matters, topics, vega_relevance,
                signal_score, content_hash, embedding
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11,
                $12, $13, $14
            )
            ON CONFLICT (url) DO NOTHING
            """,
            item.url,
            source_name,
            bucket,
            title,
            author or None,
            published_at,
            raw_text,
            tag_result.get("summary", ""),
            tag_result.get("why_it_matters", ""),
            tag_result.get("topics", []),
            vega,
            signal_score,
            content_hash,
            embedding,
        )

    logger.info("+ [%s] %s", source_name, title[:80])
    return True


# ---------------------------------------------------------------------------
# Per-source orchestration
# ---------------------------------------------------------------------------


async def _process_source(
    source: dict,
    bucket: str,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    host_last: dict[str, float],
) -> int:
    """Fetch and process one source. Returns count of new articles inserted."""
    src_type = source["type"]

    if src_type == "rss":
        items = await _get_rss_items(source["url"], client, sem, host_last)
    elif src_type == "html":
        items = await _get_html_items(source, client, sem, host_last)
    else:
        logger.warning("Unknown source type %r for %s", src_type, source["name"])
        return 0

    if not items:
        return 0

    items = items[:MAX_ITEMS_PER_SOURCE]
    tasks = [
        _process_item(item, source["name"], bucket, client, sem, host_last)
        for item in items
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_count = 0
    for r in results:
        if r is True:
            new_count += 1
        elif isinstance(r, Exception):
            logger.debug("Item error: %s", r)

    return new_count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_ingest() -> None:
    """Top-level ingestion run, called by the Modal cron or `modal run modal_app.py::ingest_now`."""
    sources_path = Path("/root/sources.yaml")
    sources: dict = yaml.safe_load(sources_path.read_text())
    logger.info(
        "Loaded %d source buckets: %s", len(sources), list(sources.keys())
    )

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    host_last: dict[str, float] = {}

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(FETCH_TIMEOUT),
    ) as client:
        total_new = 0
        for bucket_name, source_list in sources.items():
            for source in source_list:
                try:
                    n = await _process_source(
                        source, bucket_name, client, sem, host_last
                    )
                    logger.info(
                        "[%s] %-40s → %d new", bucket_name, source["name"], n
                    )
                    total_new += n
                except Exception as exc:
                    logger.warning(
                        "[%s] %s failed (skipping source): %s",
                        bucket_name,
                        source["name"],
                        exc,
                    )

    logger.info("Ingest complete — %d new articles total", total_new)
