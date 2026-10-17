-- =============================================================================
-- 002_bronze_batch_tables.sql
-- Raw landing tables for the 9 Olist source CSVs.
--
-- Bronze convention (see TUTOR.md §3): columns are TEXT, no PK/FK/CHECK
-- constraints, no deduplication. The goal is to land the source data exactly
-- as it arrived, so a bad row never blocks ingestion and nothing is silently
-- coerced or dropped. Typing, cleaning, and constraints happen in dbt staging
-- models (silver). Every table carries the same three ingestion-metadata
-- columns so batch loads are always traceable and reprocessable.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- olist_customers_dataset.csv
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.customers (
    customer_id                 TEXT,
    customer_unique_id          TEXT,
    customer_zip_code_prefix    TEXT,
    customer_city                TEXT,
    customer_state               TEXT,
    _source_file                 TEXT        NOT NULL,
    _ingested_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                     TEXT
);

-- ---------------------------------------------------------------------------
-- olist_geolocation_dataset.csv
-- Many-to-many on zip prefix; dedup happens in staging, not here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.geolocation (
    geolocation_zip_code_prefix  TEXT,
    geolocation_lat               TEXT,
    geolocation_lng               TEXT,
    geolocation_city              TEXT,
    geolocation_state             TEXT,
    _source_file                  TEXT        NOT NULL,
    _ingested_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                      TEXT
);

-- ---------------------------------------------------------------------------
-- olist_orders_dataset.csv
-- Lifecycle timestamps here are what drive the streaming/CDC simulations.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.orders (
    order_id                        TEXT,
    customer_id                     TEXT,
    order_status                    TEXT,
    order_purchase_timestamp        TEXT,
    order_approved_at               TEXT,
    order_delivered_carrier_date    TEXT,
    order_delivered_customer_date   TEXT,
    order_estimated_delivery_date   TEXT,
    _source_file                    TEXT        NOT NULL,
    _ingested_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                        TEXT
);

-- ---------------------------------------------------------------------------
-- olist_order_items_dataset.csv
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.order_items (
    order_id              TEXT,
    order_item_id          TEXT,
    product_id             TEXT,
    seller_id               TEXT,
    shipping_limit_date     TEXT,
    price                    TEXT,
    freight_value            TEXT,
    _source_file             TEXT        NOT NULL,
    _ingested_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                 TEXT
);

-- ---------------------------------------------------------------------------
-- olist_order_payments_dataset.csv
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.order_payments (
    order_id               TEXT,
    payment_sequential      TEXT,
    payment_type             TEXT,
    payment_installments     TEXT,
    payment_value             TEXT,
    _source_file              TEXT        NOT NULL,
    _ingested_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                  TEXT
);

-- ---------------------------------------------------------------------------
-- olist_order_reviews_dataset.csv
-- review_comment_message is frequently null — expected, handle in RAG step.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.order_reviews (
    review_id                  TEXT,
    order_id                    TEXT,
    review_score                 TEXT,
    review_comment_title          TEXT,
    review_comment_message         TEXT,
    review_creation_date            TEXT,
    review_answer_timestamp          TEXT,
    _source_file                     TEXT        NOT NULL,
    _ingested_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                         TEXT
);

-- ---------------------------------------------------------------------------
-- olist_products_dataset.csv
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.products (
    product_id                     TEXT,
    product_category_name           TEXT,
    product_name_lenght              TEXT,
    product_description_lenght        TEXT,
    product_photos_qty                 TEXT,
    product_weight_g                    TEXT,
    product_length_cm                    TEXT,
    product_height_cm                     TEXT,
    product_width_cm                       TEXT,
    _source_file                            TEXT        NOT NULL,
    _ingested_at                             TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                                 TEXT
);

-- ---------------------------------------------------------------------------
-- olist_sellers_dataset.csv
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.sellers (
    seller_id                  TEXT,
    seller_zip_code_prefix       TEXT,
    seller_city                    TEXT,
    seller_state                     TEXT,
    _source_file                      TEXT        NOT NULL,
    _ingested_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                           TEXT
);

-- ---------------------------------------------------------------------------
-- product_category_name_translation.csv
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.product_category_name_translation (
    product_category_name           TEXT,
    product_category_name_english     TEXT,
    _source_file                        TEXT        NOT NULL,
    _ingested_at                         TIMESTAMPTZ NOT NULL DEFAULT now(),
    _batch_id                             TEXT
);

-- ---------------------------------------------------------------------------
-- Helpful non-unique indexes for the join keys staging models will use most.
-- Not primary/foreign keys on purpose — bronze stays unconstrained; these are
-- purely to keep dbt staging model builds fast as the tables grow.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_bronze_orders_order_id            ON bronze.orders (order_id);
CREATE INDEX IF NOT EXISTS ix_bronze_orders_customer_id         ON bronze.orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_bronze_order_items_order_id       ON bronze.order_items (order_id);
CREATE INDEX IF NOT EXISTS ix_bronze_order_payments_order_id    ON bronze.order_payments (order_id);
CREATE INDEX IF NOT EXISTS ix_bronze_order_reviews_order_id     ON bronze.order_reviews (order_id);
CREATE INDEX IF NOT EXISTS ix_bronze_customers_customer_id      ON bronze.customers (customer_id);
