-- =============================================================================
-- 007_agent_checkpoints.sql
-- Storage for LangGraph checkpoints (durable agent state) in rag/agent/sql_tool.py.
--
-- Kept apart from the agent's read-only role (006) on purpose: checkpoints need
-- writes, and the SQL-running role must stay read-only. This role can write its
-- own schema only. It has no access to marts, bronze, or source_oltp.
--
-- LangGraph's PostgresSaver creates its tables in this schema on first run
-- (saver.setup()), so the role needs ownership of the schema.
--
-- As with 006, the password is not set here. Set it out of band:
--     ALTER ROLE olist_agent_state PASSWORD '...';
-- and put the connection string in .env as AGENT_CHECKPOINT_DATABASE_URL.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olist_agent_state') THEN
        CREATE ROLE olist_agent_state LOGIN;
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS agent_state AUTHORIZATION olist_agent_state;

ALTER ROLE olist_agent_state SET search_path = agent_state;
