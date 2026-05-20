-- Migration 001: add user_id to queries table
-- Run once against the live DB:
--   docker compose exec postgres psql -U postgres -d rag_db -f /migrations/001_add_user_id_to_queries.sql

ALTER TABLE queries ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);
CREATE INDEX IF NOT EXISTS ix_queries_user ON queries(user_id);
