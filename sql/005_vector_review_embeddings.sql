-- 005_vector_review_embeddings.sql
-- Embedding store for Phase 5 RAG over review text.
--
-- One row per review that has a non-null comment, embedded with the local
-- sentence-transformers model `paraphrase-multilingual-mpnet-base-v2`
-- (768 dims, handles Portuguese natively — see rag_pipeline.md for the
-- decision rationale). Populated by rag/embeddings/embed_reviews.py from
-- marts.mart_review_base, not from bronze — embeddings are a derived,
-- rebuildable artifact, not a source of truth.
--
-- Denormalized filter columns (review_score, is_late_delivery,
-- customer_state, order_purchase_timestamp) are carried alongside the
-- vector so the review-search tool can filter without joining back to
-- marts on every query.
-- =============================================================================


CREATE TABLE IF NOT EXISTS vector.review_embeddings (
    review_id                   TEXT NOT NULL,
    order_id                    TEXT NOT NULL,
    review_text                 TEXT NOT NULL,
    embedding                   VECTOR(768) NOT NULL,
    review_score                INTEGER,
    is_late_delivery            BOOLEAN,
    customer_state              TEXT,
    order_purchase_timestamp    TIMESTAMP,
    embedded_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS review_embeddings_embedding_hnsw_idx
    ON vector.review_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- Supports the review-search tool's metadata filters (e.g. "late deliveries
-- in SP with score <= 2") without a full scan.
CREATE INDEX IF NOT EXISTS review_embeddings_filters_idx
    ON vector.review_embeddings (review_score, is_late_delivery, customer_state);

