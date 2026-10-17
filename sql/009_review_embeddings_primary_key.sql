-- =============================================================================
-- 009_review_embeddings_primary_key.sql
-- Enforces the row identity of vector.review_embeddings.
--
-- A row is one review on one order: a review_id can cover several orders
-- (299 reviews do), and each of those is its own row. The key is therefore
-- (review_id, order_id), not review_text. Different reviews often share text
-- ("Recomendo", "Ótimo"), so deduplicating on text would merge unrelated rows.
--
-- Applied as the admin/owner role, since the agent roles cannot alter the table.
-- =============================================================================

ALTER TABLE vector.review_embeddings
    ADD CONSTRAINT review_embeddings_pkey PRIMARY KEY (review_id, order_id);
