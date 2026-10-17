-- =============================================================================
-- 003_bronze_streaming_table.sql
-- Landing table for the simulated order-event stream (Phase 3).
--
-- The streaming producer replays historical orders using their real
-- order_purchase_timestamp on an accelerated clock and publishes each one as
-- an event to a Kafka/Redpanda topic. The consumer reads that topic in
-- micro-batches and inserts here.
--
-- Kept as a SEPARATE bronze table from bronze.orders (not a merge into it):
-- the point of Phase 3 is to practice streaming ingestion mechanics, so this
-- table's shape mirrors what actually crosses the wire (the Kafka message),
-- including the fields that make idempotent re-processing possible.
-- =============================================================================

CREATE TABLE IF NOT EXISTS bronze.orders_stream_raw (
    -- identity of the underlying order this event describes
    order_id                    TEXT        NOT NULL,
    customer_id                  TEXT,
    order_status                  TEXT,
    order_purchase_timestamp       TEXT,

    -- Kafka delivery metadata — needed to dedupe on replay/at-least-once
    -- delivery, and to reason about consumer lag/ordering during the exercise.
    kafka_topic                     TEXT,
    kafka_partition                  INT,
    kafka_offset                      BIGINT,
    event_produced_at                  TIMESTAMPTZ,

    -- ingestion metadata, consistent with the batch bronze tables
    _source_file                        TEXT        NOT NULL DEFAULT 'kafka:orders-stream',
    _ingested_at                         TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                             TEXT,

    -- natural key for idempotent upserts: the same (topic, partition, offset)
    -- should never be applied twice even under at-least-once redelivery.
    CONSTRAINT uq_orders_stream_raw_offset UNIQUE (kafka_topic, kafka_partition, kafka_offset)
);

CREATE INDEX IF NOT EXISTS ix_bronze_orders_stream_raw_order_id
    ON bronze.orders_stream_raw (order_id);
