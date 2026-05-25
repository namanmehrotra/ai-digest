# AI Digest & Knowledge Base — Engineering Spec

**Owner:** Naman Mehrotra (@namanmehrotra)
**Status:** Draft v1 — ready for implementation
**Last updated:** 2026-05-25
**Repo:** `github.com/namanmehrotra/ai-digest` (to be created, separate from Vega Claims, MIT or similar — open-sourceable later)

---

## 1. Problem

I want to stay current with frontier AI work — frontier lab releases, what practitioners are actually trying, empirical findings from papers, and material industry news — without being an active Twitter user, without drowning in email, and without the time budget of a fast reader. Existing newsletters are noisy, duplicate each other, and lack a "skip unless" hierarchy. Twitter has the practitioner signal but is hostile to skim-on-a-schedule consumption.

A second, longer-arc need: I want a personal corpus of what's happened in AI that I can query while building. When I'm writing a feature at Vega Claims or hacking on something personal in Claude Code, I want to ask "what's the current best-practice for X" and get an answer grounded in *what I've actually been tracking* — not generic web search results.

## 2. Solution summary

Three loosely-coupled components, deployed as a standalone product I own, independent of any chat session or Claude account:

1. **Ingestion + digest pipeline** — a cron job that fetches a curated source list every ~12 hours, deduplicates and stores each item, and twice a week (Tue + Fri mornings) synthesizes a compressed email digest with strict format rules.
2. **High-signal interrupt** — a separate, rare email that fires only when corroborated signals trip a threshold (frontier model launch, viral paper, etc.).
3. **Knowledge base + MCP server** — every ingested item lives in Postgres with vector embeddings. An MCP server exposes search/query tools so Claude Code, Cowork, and any other MCP-aware agent can pull from the corpus while I'm building.

## 3. Goals & non-goals

### Goals
- Reliable email delivery on a Tue/Fri 7am ET schedule, even when my laptop is off.
- Compression across sources — I should never read the same news twice.
- Format optimized for slow reading: TL;DR + ≤12 items + "skip unless" tags + 2 lines per item.
- Persistent KB that grows in value over time.
- Queryable from inside any MCP-aware client.
- Independently operable (no dependency on Cowork / claude.ai / any single chat session).
- Sub-$10/month operating cost at this scale.

### Non-goals (for v1)
- Multi-user. This is a tool of one.
- Web chat UI. Considered post-MVP; MCP first.
- Twitter/X firehose ingestion. We cover the practitioner layer via the durable-writing proxy (Substacks, blogs, HN, GitHub).
- Real-time push. Twice-weekly + interrupt is enough.
- Mobile push notifications. Email is the channel.
- Paywalled content (The Information, Stratechery body). Headlines only for those.

## 4. User stories

- *As Naman, on a Tuesday or Friday morning, I open my personal Gmail and see a single AI digest email at the top of my inbox. I can read it fully in 3–5 minutes. I know which items to skip because of clear tags.*
- *As Naman, when a frontier model drops mid-week, I get a separate interrupt email within ~12 hours of the news propagating across multiple practitioner blogs.*
- *As Naman, while building a feature in Claude Code, I ask the agent to "check my AI knowledge base for current best practices on evals" and it queries the MCP server and returns grounded, attributable answers.*
- *As Naman, three months in, the KB has ~1500 articles, the digest format is tuned to what I actually read, and the MCP server is part of my default Claude Code config.*

## 5. System architecture

```
                    ┌─────────────────────────────┐
                    │      Source list (YAML)     │
                    └──────────────┬──────────────┘
                                   │
                ┌──────────────────▼──────────────────┐
                │   Ingestion pipeline (Modal cron)   │
                │   every 12h: fetch → extract →      │
                │   dedup → tag → embed → store       │
                └──────────────────┬──────────────────┘
                                   │
                  ┌────────────────▼────────────────┐
                  │  Neon Postgres + pgvector       │
                  │  articles, embeddings, digests, │
                  │  query_logs                     │
                  └──┬──────────────┬───────────────┘
                     │              │
        ┌────────────▼─┐         ┌──▼──────────────────────┐
        │ Digest job   │         │ MCP server (Modal HTTPS)│
        │ (Modal cron, │         │ - search_ai_knowledge   │
        │  Tue/Fri 7am)│         │ - get_recent_articles   │
        └──────┬───────┘         │ - synthesize_topic      │
               │                 └──┬──────────────────────┘
        ┌──────▼───────┐            │
        │ Resend API   │            │ Claude Code / Cowork /
        │ → personal   │            │ Cursor / etc. via MCP
        │   Gmail      │            │
        └──────────────┘            │

        ┌──────────────────────────┐
        │ High-signal monitor      │ ◄── runs after every
        │ (cooldown: 1 / 24h)      │     ingestion pass
        │ → interrupt email        │
        └──────────────────────────┘
```

## 6. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Best ingestion/RAG ecosystem; Modal is Python-native |
| Compute / cron | Modal | Serverless, Python-native cron, scales to zero, free tier |
| Database | Neon Postgres + `pgvector` | Free tier, branchable, vector + metadata in one place |
| LLM (synthesis, tagging) | Anthropic Claude API (Sonnet for synthesis, Haiku for tagging) | Cost/quality split |
| Embeddings | Voyage AI (`voyage-3.5` or current best) | Anthropic-recommended, generous free tier, strong retrieval |
| Email send | Resend | Clean API, good deliverability, 3k/month free |
| Content extraction | `trafilatura` | Best-in-class boilerplate removal |
| RSS / feeds | `feedparser` | Standard |
| HTTP | `httpx` (async) | Modern, async |
| MCP server | Anthropic MCP Python SDK | Official, well-supported |
| Secrets | Modal secrets | Built-in, no extra infra |
| Deployment | `modal deploy` from GitHub Actions on push to `main` | Simple CI |

**Rejected alternatives & why:**
- *TypeScript / Cloudflare Workers stack* — ingestion ecosystem is thinner; Modal's cron ergonomics beat Workers cron + Trigger.dev for this scale.
- *LangChain / LlamaIndex* — too much abstraction for this; we'll call SDKs directly.
- *Pinecone* — overkill and adds cost; pgvector is sufficient at our scale.
- *OpenAI embeddings* — fine choice, but Voyage is the natural pair when the rest of the stack is Anthropic and the free tier is more generous.
- *Self-hosted vector DB (Qdrant, Weaviate)* — extra ops surface area for no benefit at this scale.

## 7. Source list (starter)

YAML-driven. The system reads `sources.yaml` at the repo root. Easy to add/remove sources without code changes.

```yaml
frontier_labs:
  - name: Anthropic News
    url: https://www.anthropic.com/news
    type: html
  - name: OpenAI Blog
    url: https://openai.com/blog/rss.xml
    type: rss
  - name: Google DeepMind Blog
    url: https://deepmind.google/discover/blog/
    type: html
  - name: Meta AI
    url: https://ai.meta.com/blog/
    type: html
  - name: Mistral News
    url: https://mistral.ai/news/
    type: html
  - name: AI2 Blog
    url: https://allenai.org/blog
    type: html
  - name: xAI News
    url: https://x.ai/news
    type: html

practitioners:
  - name: Simon Willison
    url: https://simonwillison.net/atom/everything/
    type: rss
  - name: One Useful Thing (Ethan Mollick)
    url: https://www.oneusefulthing.org/feed
    type: rss
  - name: Interconnects (Nathan Lambert)
    url: https://www.interconnects.ai/feed
    type: rss
  - name: Latent Space (Swyx)
    url: https://www.latent.space/feed
    type: rss
  - name: Eugene Yan
    url: https://eugeneyan.com/rss/
    type: rss
  - name: Hamel Husain
    url: https://hamel.dev/index.xml
    type: rss
  - name: Jason Liu
    url: https://jxnl.co/feeds/feed.xml
    type: rss
  - name: Sebastian Raschka — Ahead of AI
    url: https://magazine.sebastianraschka.com/feed
    type: rss
  - name: Lilian Weng
    url: https://lilianweng.github.io/index.xml
    type: rss

papers:
  - name: HuggingFace Daily Papers
    url: https://huggingface.co/papers
    type: html
  - name: arxiv-sanity top
    url: https://arxiv-sanity-lite.com/?rank=time
    type: html
  - name: AlphaSignal
    url: https://alphasignal.ai
    type: html  # weekly newsletter mirror

industry:
  - name: TechCrunch AI
    url: https://techcrunch.com/category/artificial-intelligence/feed/
    type: rss
  - name: The Verge AI
    url: https://www.theverge.com/rss/ai-artificial-intelligence/index.xml
    type: rss

community_signals:
  - name: HackerNews — AI-filtered top
    url: https://hnrss.org/frontpage?q=AI+OR+LLM+OR+Claude+OR+GPT+OR+Anthropic+OR+OpenAI
    type: rss
  - name: GitHub trending — Python AI
    url: https://github.com/trending/python?since=daily
    type: html
```

Source list is intentionally Twitter-free. Practitioner signal is captured by the durable-writing proxy (these folks all blog/Substack).

## 8. Data model

```sql
-- articles: every piece of content ever ingested
CREATE TABLE articles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url             TEXT NOT NULL UNIQUE,
  source_name     TEXT NOT NULL,
  source_bucket   TEXT NOT NULL CHECK (source_bucket IN
                    ('frontier_labs','practitioners','papers','industry','community_signals')),
  title           TEXT NOT NULL,
  author          TEXT,
  published_at    TIMESTAMPTZ,
  ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  raw_text        TEXT NOT NULL,
  summary         TEXT,                  -- 1-2 line LLM summary, generated at ingest
  why_it_matters  TEXT,                  -- 1 line LLM-generated relevance hook
  topics          TEXT[],                -- e.g. ['evals','agent-building','model-launch']
  vega_relevance  TEXT CHECK (vega_relevance IN ('general','claims','agent-building','high')),
  signal_score    REAL NOT NULL DEFAULT 0,    -- 0..1, see scoring section
  content_hash    TEXT NOT NULL,         -- sha256 of normalized text, for dedup
  embedding       VECTOR(1024)           -- voyage-3 dimension
);

CREATE INDEX articles_published_idx     ON articles (published_at DESC);
CREATE INDEX articles_source_bucket_idx ON articles (source_bucket);
CREATE INDEX articles_topics_idx        ON articles USING GIN (topics);
CREATE INDEX articles_embedding_idx     ON articles USING hnsw (embedding vector_cosine_ops);

-- digests: one row per sent digest
CREATE TABLE digests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind            TEXT NOT NULL CHECK (kind IN ('scheduled','high_signal')),
  sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  subject         TEXT NOT NULL,
  body_md         TEXT NOT NULL,
  body_html       TEXT NOT NULL,
  article_ids     UUID[] NOT NULL,
  resend_message_id TEXT
);

-- query_logs: every MCP / chat query, for future tuning
CREATE TABLE query_logs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source          TEXT NOT NULL,         -- 'mcp','web','cli'
  query           TEXT NOT NULL,
  retrieved_ids   UUID[],
  answer_md       TEXT
);

-- high_signal_state: last interrupt time for cooldown enforcement
CREATE TABLE high_signal_state (
  id              SERIAL PRIMARY KEY,
  last_fired_at   TIMESTAMPTZ
);
```

## 9. Components

### 9.1 Ingestion pipeline

**Schedule:** Modal cron, every 12 hours (0 0,12 * * *) UTC.

**Per-source flow:**
1. Fetch via `httpx` (or `feedparser` for RSS).
2. Parse listing → enumerate item URLs.
3. For each item URL: fetch full page, run `trafilatura.extract()` to get clean text.
4. Compute `content_hash` over normalized text.
5. **Dedup check:** if URL or content_hash already in `articles`, skip.
6. **Tagging (Claude Haiku):** single batched call returning `{summary, why_it_matters, topics, vega_relevance}` per new article. Keep prompt short and cheap.
7. **Embedding:** call Voyage `voyage-3.5` on `title + summary + raw_text[:8000]`.
8. **Insert** into `articles`.

**Failure handling:** any individual source failure is logged and skipped; the run continues. A source that fails 5 consecutive runs raises a Modal notification (email to self).

**Rate limiting:** sequential fetches with 1s jitter per source. We're not hammering anyone.

**Robots / etiquette:** respect `robots.txt`. Honor `noai` meta tags. Set a clear `User-Agent: ai-digest-personal/1.0 (+github.com/namanmehrotra/ai-digest)`.

### 9.2 Signal scoring

Each new article gets a `signal_score` in [0, 1] computed at ingest time:

```
signal_score =
    0.35 * cross_source_count_norm    # how many other sources mentioned it (URL/title fuzzy match) in last 7 days
  + 0.25 * source_authority_weight    # static weights per source in sources.yaml
  + 0.20 * recency_decay              # exp decay over 72h
  + 0.10 * keyword_boost              # frontier model names, "release", "paper", named labs
  + 0.10 * vega_relevance_boost       # boost for claims-relevant or agent-building items
```

Stored on the article. Used both by the digest selector and the high-signal monitor.

### 9.3 Digest pipeline

**Schedule:** Modal cron, Tue + Fri at 12:00 UTC (~7am ET / 8am summer).

**Flow:**
1. Query articles since last `digests.sent_at` (kind = 'scheduled'), ordered by `signal_score DESC`.
2. Group by `source_bucket`. Cap at 12 total items (3 per bucket max, then fill from highest-signal remaining).
3. Send the grouped list to Claude Sonnet with the format prompt (see §10). Sonnet returns Markdown.
4. Render Markdown → HTML with a minimal template (no images, no tracking pixels).
5. Send via Resend API to `namanmehrotra95@gmail.com` (configurable in env).
6. Store the digest row.

**Prompt for synthesis:**

```
You are writing Naman's twice-weekly AI digest. Output ONLY the digest, no preamble.

RULES:
- TL;DR section at the top: 3 lines max, the most important things across all items.
- One section per bucket, in this order: Frontier launches, Practitioner experiments, Papers, Industry.
- Each item: 1 line "what happened" + 1 line "why it matters / skip unless [X]". Max 2 lines.
- End each item with a [link](url) and tags like `[claims]` `[agent-building]` `[general]`.
- No filler, no emojis, no "Hi Naman", no sign-off.
- Total length under 600 words.
- If a bucket has nothing worth including, omit the section entirely.

Items provided below (signal-ranked):
{items_json}
```

### 9.4 High-signal monitor

After each ingestion pass:
1. Find articles ingested in last 12h with `signal_score > 0.75` OR `cross_source_count >= 4`.
2. Check `high_signal_state.last_fired_at` — if within last 24h, skip (cooldown).
3. If we have ≥1 qualifying article and cooldown is clear: synthesize a short interrupt email (1–3 items, ~150 words), send via Resend, update state.

**Bias toward false negatives:** better to miss one interrupt than to over-fire. The Tue/Fri digest is the catch-net.

### 9.5 MCP server

Modal-hosted HTTPS endpoint, MCP protocol over HTTP+SSE. Bearer token auth (token in `Authorization` header).

**Exposed tools:**

1. `search_ai_knowledge(query: str, filters?: { source_bucket?: str, topics?: str[], since?: ISO8601, limit?: int }) -> list[Article]`
   - Embeds query with Voyage, runs cosine-similarity search over `articles.embedding`, applies metadata filters, returns top-N with `{title, url, source_name, published_at, summary, why_it_matters, topics}`.

2. `get_recent_articles(bucket?: str, topic?: str, days?: int = 7, limit?: int = 20) -> list[Article]`
   - Plain metadata filter, no semantic search. For "show me what's new in evals this week."

3. `synthesize_topic(topic: str, days?: int = 30) -> { summary_md: str, sources: list[Article] }`
   - Retrieves all articles matching `topic` in the window, asks Claude Sonnet to write a 1-page synthesis with citations, returns markdown.

4. `get_recent_digests(limit?: int = 4) -> list[Digest]`
   - Returns past digest bodies.

**Local install snippet** (for Claude Code's `~/.claude.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "ai-digest": {
      "transport": "http",
      "url": "https://<modal-app-name>.modal.run/mcp",
      "headers": { "Authorization": "Bearer ${AI_DIGEST_MCP_TOKEN}" }
    }
  }
}
```

## 10. Email format

**Subject line:** `AI Digest — Tue May 26` (date of send, no clickbait).

**Body:**

```
TL;DR
- [1-line headline 1]
- [1-line headline 2]
- [1-line headline 3]

Frontier launches
- Title (linked): one line of what + one line of why-it-matters / skip unless X.  [tags]
- ...

Practitioner experiments
- ...

Papers
- ...

Industry
- ...

—
Reply with a topic to get more of it next time. Reply STOP to pause for a week.
```

**Hard caps:** ≤12 items, ≤600 words, no images, no tracking pixels.

**High-signal interrupt format:**

```
Subject: AI Digest — high signal: <event headline>

<1-paragraph what happened, 50 words>

Why it matters: <1-2 sentences>

Sources:
- Title 1 (linked)
- Title 2 (linked)
```

## 11. Deployment

**Repo layout:**

```
ai-digest/
├── README.md
├── SPEC.md                       # this file
├── pyproject.toml
├── sources.yaml
├── modal_app.py                  # Modal app + cron definitions
├── src/
│   ├── ingest/
│   │   ├── fetcher.py
│   │   ├── extractor.py
│   │   ├── tagger.py
│   │   └── embedder.py
│   ├── scoring.py
│   ├── digest/
│   │   ├── selector.py
│   │   ├── synthesizer.py
│   │   └── sender.py
│   ├── high_signal.py
│   ├── mcp_server.py
│   ├── db.py
│   └── prompts/
│       ├── tagging.md
│       ├── digest.md
│       └── topic_synthesis.md
├── migrations/
│   └── 001_init.sql
├── tests/
│   └── ...
└── .github/workflows/
    └── deploy.yml                # modal deploy on push to main
```

**Deployment flow:**
1. `modal deploy modal_app.py` — deploys all functions, cron schedules, and the MCP HTTP endpoint.
2. Modal secrets hold all API keys; rotated via the Modal dashboard.
3. Neon DB runs continuously; pgvector enabled at provision.
4. GitHub Actions runs `modal deploy` on push to `main`. No other CI needed for v1.

## 12. Secrets

Stored as a single Modal secret named `ai-digest-prod`:

```
ANTHROPIC_API_KEY         = sk-ant-...
VOYAGE_API_KEY            = pa-...
RESEND_API_KEY            = re_...
DATABASE_URL              = postgresql://...neon.tech/ai-digest?sslmode=require
MCP_BEARER_TOKEN          = <generated 32-byte random>
DIGEST_RECIPIENT_EMAIL    = namanmehrotra95@gmail.com
DIGEST_FROM_EMAIL         = digest@<your-domain>.com   (Resend verified)
```

A `from` domain you control is required for Resend deliverability. If you don't want to set up a custom domain immediately, Resend lets you use `onboarding@resend.dev` for testing; for prod we verify a domain you own (or a subdomain like `digest.namanmehrotra.com`).

## 13. Build sequence

**Phase 1 — Week 1: Digest MVP**
- Scaffold repo, install deps, configure Modal account
- Implement ingestion for ~6 RSS sources (start with practitioners + 2 lab feeds)
- Postgres schema + migrations
- Tagging via Haiku
- Digest selector + Sonnet synthesis
- Resend send
- Cron schedule Tue/Fri
- **Exit criteria:** real email lands in personal Gmail Tue & Fri for one full week with the right format. No KB chat yet.

**Phase 2 — Week 2: Knowledge persistence + signal**
- Embeddings via Voyage on ingest
- pgvector index
- Signal scoring fully wired
- High-signal monitor with cooldown
- All starter sources online
- **Exit criteria:** KB has ≥200 articles; high-signal monitor has fired at least once (or quiet by design); signal scores look sane in spot-checks.

**Phase 3 — Week 3: MCP server**
- HTTP MCP endpoint on Modal
- Bearer auth
- Four MCP tools live
- Installed in Claude Code locally
- **Exit criteria:** I can ask "what's been happening with evals lately" inside Claude Code and get a grounded answer from my own corpus.

**Phase 4 — Later: tuning & extensions**
- Pre-synthesized topic notes (background job that writes a "current state of X" when a topic accumulates enough material)
- Feedback loop: parse digest reply emails for tag-tuning signals
- Simple web chat (FastAPI + HTMX) on the same backend
- Possibly add Twitter ingestion via a paid API if the durable-writing proxy proves insufficient

## 14. Setup checklist (do before coding)

Before Claude Code starts building, Naman needs to create accounts and gather:

- [ ] **GitHub repo** `namanmehrotra/ai-digest` (empty, private to start)
- [ ] **Anthropic API key** — console.anthropic.com → new workspace `ai-digest` → API key → $20 monthly limit
- [ ] **Voyage AI API key** — voyageai.com → sign up → API key (free tier is generous)
- [ ] **Modal account** — modal.com → sign up (free tier covers this workload)
- [ ] **Neon account** — neon.tech → new project `ai-digest` → enable `pgvector` extension → copy `DATABASE_URL`
- [ ] **Resend account** — resend.com → sign up → verify a sending domain (or accept the test sender for week 1)
- [ ] **Random MCP bearer token** — `openssl rand -hex 32` and save it

Once those exist, Claude Code can scaffold the repo, write Phase 1, and ship the first real digest within a few sessions.

## 15. Locked decisions (resolved 2026-05-25)

1. **Sending domain:** Use Resend's test sender `onboarding@resend.dev` for v1. This restricts delivery to Naman's verified personal address (`namanmehrotra95@gmail.com`), which is fine — there are no other recipients. Revisit once we want to share digests externally or add a public archive; verifying a subdomain of a personal domain is a ~10-minute follow-up at that point.
2. **Claims-relevance signal:** Single broad `claims` tag in `articles.topics` for v1. Do not pre-build a finer taxonomy (commercial auto, workers' comp, etc.) — wait until 4–6 weeks of real ingestion show which sub-themes actually emerge, then split.
3. **Topic taxonomy:** Fixed initial set: `evals`, `agent-building`, `prompt-engineering`, `model-launch`, `RL`, `multimodal`, `infra`, `safety`, `business`, `claims`. New tags are added by the tagger only after the same novel tag candidate appears in 3+ articles within a 30-day window (logged for review, not silently inserted).
4. **Feedback loop UX:** Parse plaintext email replies. The recipient address has an inbound webhook configured at Resend; any reply runs through a lightweight intent classifier (Haiku) that emits `{intent: "more"|"less"|"stop"|"feedback", topic?: str}` and updates per-topic weight multipliers used in `signal_score`. No web preferences page in v1.
5. **Web chat:** Deferred. MCP server is the primary query interface. Revisit only if MCP turns out insufficient.
6. **Self-syndication / public archive:** No. Digests live only in inbox + KB. No `public_slug` field in the schema.

### Future considerations (not in v1 scope)
- Custom sending domain (`digest@<personal-domain>`) — track as a 1-day follow-up task once the project is stable.
- Pre-synthesized "current state of X" topic notes (mentioned in §13 Phase 4).
- Twitter/X firehose ingestion — only if the durable-writing proxy proves materially insufficient.
- Multi-recipient support — would require domain verification first.

---

**End of spec.** Open this in Claude Code with:

> Implement Phase 1 of SPEC.md. Scaffold the repo at github.com/namanmehrotra/ai-digest, write the ingestion pipeline for the practitioner sources first, and get a real digest email landing in my personal Gmail by end of session. The Modal secret `ai-digest-prod` is already populated.
