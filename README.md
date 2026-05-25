# ai-digest

Personal AI digest + knowledge base. Twice-weekly email digest of frontier AI work, plus an MCP server for querying the corpus while building.

## What this is

A standalone product that:

1. Ingests a curated set of AI sources (frontier labs, practitioner blogs, papers, industry news) every 12 hours.
2. Sends a compressed email digest every Tuesday and Friday morning.
3. Fires a high-signal interrupt email when something material happens mid-cycle.
4. Persists every article in a Postgres + pgvector knowledge base.
5. Exposes that KB via an MCP server, so Claude Code (or any MCP client) can query it inline while building.

Designed for a single user. Open-sourceable.

## Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Compute / cron / HTTPS | Modal |
| Database | Neon Postgres + pgvector |
| LLM | Anthropic Claude API (Sonnet 4.6 synthesis, Haiku 4.5 tagging) |
| Embeddings | Voyage AI (`voyage-3.5`, 1024 dims) |
| Email | Resend |
| Content extraction | trafilatura |
| RSS | feedparser |
| HTTP | httpx |
| Query interface | MCP (Anthropic SDK) |

## Architecture

```
sources.yaml
    │
    ▼
Modal cron (every 12h)
    │
    ▼
ingest pipeline (fetch → extract → dedup → tag → embed) ──► Neon Postgres + pgvector
                                                                  │
              ┌───────────────────────────────────────────────────┼───────────────┐
              ▼                                                   ▼               ▼
       Tue/Fri digest job                              High-signal monitor   MCP server (HTTPS)
              │                                                   │               │
              ▼                                                   ▼               ▼
            Resend ───────────────► personal Gmail            Resend           Claude Code / Cursor / Cowork
```

## Setup

See `SPEC.md` for the full engineering spec.

```bash
# 1. Install Modal CLI and authenticate
pip install modal
modal token new

# 2. Create the secret bundle
modal secret create ai-digest-prod \
  ANTHROPIC_API_KEY=... \
  VOYAGE_API_KEY=... \
  RESEND_API_KEY=... \
  DATABASE_URL=... \
  MCP_BEARER_TOKEN=... \
  DIGEST_RECIPIENT_EMAIL=... \
  DIGEST_FROM_EMAIL=onboarding@resend.dev

# 3. Run the DB migration (one-time)
psql "$DATABASE_URL" -f migrations/001_init.sql

# 4. Deploy to Modal
modal deploy modal_app.py
```

## Manual triggers (for testing)

```bash
modal run modal_app.py::ingest_now
modal run modal_app.py::digest_now
```

## MCP server usage

Once deployed, add to `~/.claude.json` or project `.mcp.json`:

```json
{
  "mcpServers": {
    "ai-digest": {
      "transport": "http",
      "url": "https://<modal-app>.modal.run/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

Exposed tools:
- `search_ai_knowledge(query, filters?)` — semantic + filtered search
- `get_recent_articles(bucket?, topic?, days?, limit?)` — metadata filter only
- `synthesize_topic(topic, days?)` — 1-page synthesis with citations
- `get_recent_digests(limit?)` — recent digest bodies

## Build phases

- **Phase 1** — ingestion + scheduled digest (Resend test sender)
- **Phase 2** — embeddings + signal scoring + high-signal monitor
- **Phase 3** — MCP server live in Claude Code
- **Phase 4** — pre-synthesized topic notes, feedback loop, web chat

## License

MIT
