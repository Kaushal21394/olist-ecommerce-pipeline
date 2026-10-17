-- =============================================================================
-- 004_source_oltp_cdc_table.sql
-- The simulated "live" OLTP table that Debezium watches for CDC (Phase 4).
--
-- This table stands in for a real production orders table. A separate script
-- replays each order's real status transitions (purchase -> approved ->
-- carrier -> delivered) as UPDATEs against this table over time. Debezium's
-- Postgres connector reads those changes from the write-ahead log and
-- publishes them to Kafka; a downstream consumer/dbt snapshot applies them
-- as SCD2 history into silver.
--
-- Lives in its own schema (source_oltp) to make the "this is standing in for
-- an external production database" boundary explicit — it is conceptually
-- outside the platform, not a bronze table.
-- =============================================================================

CREATE TABLE IF NOT EXISTS source_oltp.orders_live_status (
    order_id                        TEXT PRIMARY KEY,
    customer_id                     TEXT        NOT NULL,
    order_status                    TEXT        NOT NULL,
    order_purchase_timestamp        TIMESTAMPTZ NOT NULL,
    order_approved_at               TIMESTAMPTZ,
    order_delivered_carrier_date    TIMESTAMPTZ,
    order_delivered_customer_date   TIMESTAMPTZ,
    order_estimated_delivery_date   TIMESTAMPTZ,
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- REPLICA IDENTITY FULL is required for Debezium to capture the full "before"
-- image on UPDATE/DELETE (not just the primary key) — without this, CDC
-- events for updated columns other than the PK come through incomplete.
ALTER TABLE source_oltp.orders_live_status REPLICA IDENTITY FULL;

-- Debezium's Postgres connector needs a replication slot and publication.
-- Run these once the table is seeded and before starting the connector.
-- (Requires wal_level = logical in postgresql.conf, set in docker-compose.)
--
--   CREATE PUBLICATION olist_cdc_publication FOR TABLE source_oltp.orders_live_status;
--
-- The replication slot itself is typically created automatically by the
-- Debezium connector on first startup (slot.name in the connector config) —
-- create it manually only if you need to inspect/manage it ahead of time:
--
--   SELECT pg_create_logical_replication_slot('olist_debezium_slot', 'pgoutput');
