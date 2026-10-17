-- =============================================================================
-- 008_agent_review_search_grants.sql
-- Lets the agent's read-only role (006) search review embeddings for the
-- Phase 5 review-search tool (rag/agent/review_search_tool.py).
--
-- Read-only, and only the one table. The role still has no access to bronze,
-- source_oltp, or the rest of the vector schema (there is nothing else in it).
-- =============================================================================

GRANT USAGE ON SCHEMA vector TO olist_agent_ro;
GRANT SELECT ON vector.review_embeddings TO olist_agent_ro;
