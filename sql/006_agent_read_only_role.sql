-- =============================================================================
-- 006_agent_read_only_role.sql
-- Least-privilege role for the Phase 5 text-to-SQL agent (rag/agent/sql_tool.py).
--
-- The agent must NOT use the superuser creds in .env. This role can read the
-- marts schema and nothing else, and its sessions are read-only by default.
--
-- Run as the owner of the dbt-built marts tables (the user dbt runs as), so the
-- ALTER DEFAULT PRIVILEGES below applies to tables dbt creates on later runs.
--
-- The password is NOT set here so no secret lands in the repo. After running
-- this file, set it once out of band:
--     ALTER ROLE olist_agent_ro PASSWORD '...';
-- and put the connection string in .env as AGENT_DATABASE_URL.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olist_agent_ro') THEN
        CREATE ROLE olist_agent_ro LOGIN;
    END IF;
END
$$;

-- Defense in depth: even if a bad query slips past the Python validator, the
-- database refuses writes and runaway queries.
ALTER ROLE olist_agent_ro SET default_transaction_read_only = on;
ALTER ROLE olist_agent_ro SET statement_timeout = '10s';
ALTER ROLE olist_agent_ro SET search_path = marts;

-- Read access to marts only. No access to bronze, source_oltp, silver/staging,
-- or the public schema beyond the default CONNECT privilege.
GRANT USAGE ON SCHEMA marts TO olist_agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO olist_agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO olist_agent_ro;