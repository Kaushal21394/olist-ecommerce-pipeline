-- =============================================================================
-- 001_schemas_and_extensions.sql
-- Creates the schemas used across the platform and required Postgres extensions.
--
-- Layout:
--   bronze       -- raw, immutable landing tables (batch + streaming + CDC land here)
--   source_oltp  -- simulated live OLTP source table that Debezium watches for CDC
--   silver, gold -- NOT created here: dbt manages these automatically based on
--                   model materialization config (custom schema per dbt convention)
--   vector       -- pgvector embeddings for RAG, created when Phase 5 lands
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS source_oltp;
CREATE SCHEMA IF NOT EXISTS vector;

-- pgvector: powers the RAG embeddings table (Phase 5). Enabled here so it's
-- available from day one without a later migration.
CREATE EXTENSION IF NOT EXISTS vector;

-- wal2json is optional (pgoutput, the built-in logical decoding plugin, works
-- fine with Debezium's Postgres connector). Uncomment only if you specifically
-- want the wal2json plugin instead of pgoutput.
-- CREATE EXTENSION IF NOT EXISTS wal2json;
