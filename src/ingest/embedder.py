"""Voyage AI embeddings — voyage-3.5, 1024 dims."""

from __future__ import annotations

import os

import voyageai

_client: voyageai.AsyncClient | None = None


def _get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        _client = voyageai.AsyncClient(api_key=os.environ["VOYAGE_API_KEY"])
    return _client


async def embed_document(text: str) -> list[float]:
    """Embed an article for storage in pgvector. Uses input_type='document'."""
    client = _get_client()
    result = await client.embed(
        texts=[text[:24000]],
        model="voyage-3.5",
        input_type="document",
    )
    return result.embeddings[0]


async def embed_query(query: str) -> list[float]:
    """Embed a search query. Uses input_type='query' for asymmetric retrieval."""
    client = _get_client()
    result = await client.embed(
        texts=[query],
        model="voyage-3.5",
        input_type="query",
    )
    return result.embeddings[0]
