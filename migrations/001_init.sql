-- Initial schema for ai-digest. See SPEC.md §8.
-- Run with: psql "$DATABASE_URL" -f migrations/001_init.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- ARTICLES: every piece of content ever ingested
CREATE TABLE IF NOT EXISTS articles (
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
  summary         TEXT,
  why_it_matters  TEXT,
  topics          TEXT[] NOT NULL DEFAULT '{}',
  vega_relevance  TEXT CHECK (vega_relevance IN ('general','claims','agent-building','high')),
  signal_score    REAL NOT NULL DEFAULT 0,
  content_hash    TEXT NOT NULL,
  embedding       VECTOR(1024)
);

CREATE INDEX IF NOT EXISTS articles_published_idx     ON articles (published_at DESC);
CREATE INDEX IF NOT EXISTS articles_ingested_idx      ON articles (ingested_at DESC);
CREATE INDEX IF NOT EXISTS articles_source_bucket_idx ON articles (source_bucket);
CREATE INDEX IF NOT EXISTS articles_topics_idx        ON articles USING GIN (topics);
CREATE INDEX IF NOT EXISTS articles_signal_idx        ON articles (signal_score DESC);
CREATE INDEX IF NOT EXISTS articles_content_hash_idx  ON articles (content_hash);
CREATE INDEX IF NOT EXISTS articles_embedding_idx     ON articles USING hnsw (embedding vector_cosine_ops);

-- DIGESTS: one row per sent digest
CREATE TABLE IF NOT EXISTS digests (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind                TEXT NOT NULL CHECK (kind IN ('scheduled','high_signal')),
  sent_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  subject             TEXT NOT NULL,
  body_md             TEXT NOT NULL,
  body_html           TEXT NOT NULL,
  article_ids         UUID[] NOT NULL,
  resend_message_id   TEXT
);

CREATE INDEX IF NOT EXISTS digests_sent_at_idx ON digests (sent_at DESC);
CREATE INDEX IF NOT EXISTS digests_kind_idx    ON digests (kind);

-- QUERY_LOGS: every MCP / chat query, for future tuning
CREATE TABLE IF NOT EXISTS query_logs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source          TEXT NOT NULL,
  query           TEXT NOT NULL,
  retrieved_ids   UUID[],
  answer_md       TEXT
);

CREATE INDEX IF NOT EXISTS query_logs_asked_at_idx ON query_logs (asked_at DESC);

-- HIGH_SIGNAL_STATE: last interrupt time for cooldown enforcement
CREATE TABLE IF NOT EXISTS high_signal_state (
  id              SERIAL PRIMARY KEY,
  last_fired_at   TIMESTAMPTZ
);

-- Seed one row so we can always UPDATE rather than UPSERT
INSERT INTO high_signal_state (id, last_fired_at) VALUES (1, NULL)
ON CONFLICT (id) DO NOTHING;

-- TOPIC_WEIGHTS: per-topic multiplier learned from email-reply feedback (Phase 4)
CREATE TABLE IF NOT EXISTS topic_weights (
  topic       TEXT PRIMARY KEY,
  weight      REAL NOT NULL DEFAULT 1.0,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
