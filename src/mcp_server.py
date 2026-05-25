"""MCP server exposing the AI knowledge base as tools. See SPEC §9.5.

Phase 3 implementation.

Exposed tools:
  - search_ai_knowledge(query, filters?)
  - get_recent_articles(bucket?, topic?, days?, limit?)
  - synthesize_topic(topic, days?)
  - get_recent_digests(limit?)

Auth: bearer token in Authorization header, checked against MCP_BEARER_TOKEN env.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

server: Server = Server("ai-digest")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_ai_knowledge",
            description=(
                "Semantic + filtered search over the AI knowledge base. Use this to look up "
                "best practices, recent findings, or what the frontier has been doing on a topic."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source_bucket": {
                        "type": "string",
                        "enum": ["frontier_labs", "practitioners", "papers", "industry", "community_signals"],
                    },
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "since": {"type": "string", "format": "date-time"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_recent_articles",
            description="List recent articles by metadata filter (no semantic search).",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string"},
                    "topic": {"type": "string"},
                    "days": {"type": "integer", "default": 7},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="synthesize_topic",
            description="Generate a 1-page synthesis of a topic from KB articles, with citations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "days": {"type": "integer", "default": 30},
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="get_recent_digests",
            description="Return the bodies of the last N digests sent.",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 4}},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch each MCP tool call to the appropriate handler.

    TODO: Phase 3 — implement each handler:
      - search_ai_knowledge: embed query (voyage), cosine search in pgvector, apply filters
      - get_recent_articles: SELECT with metadata filters
      - synthesize_topic: retrieve articles, call Claude Sonnet with topic_synthesis.md prompt
      - get_recent_digests: SELECT from digests table
    """
    raise NotImplementedError(f"Tool {name!r} not yet implemented")


def build_app() -> Starlette:
    """Build the ASGI app served by Modal."""
    expected_token = os.environ["MCP_BEARER_TOKEN"]
    transport = SseServerTransport("/messages")

    async def handle_sse(request: Request) -> Response:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != expected_token:
            return Response(status_code=401, content="Unauthorized")
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (r, w):
            await server.run(r, w, server.create_initialization_options())
        return Response()

    return Starlette(
        routes=[
            Route("/mcp", endpoint=handle_sse),
            Mount("/messages", app=transport.handle_post_message),
        ]
    )
