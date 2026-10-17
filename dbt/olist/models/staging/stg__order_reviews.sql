-- review_id alone is not unique (a review can cover several orders): grain is (review_id, order_id).
-- Some orders also have >1 review; resolved to one per order in int_order_reviews_agg.
with source as (

    select * from {{ source('olist','order_reviews') }}

)

select
    review_id,
    order_id,
    review_score::int                       as review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date::timestamp         as review_creation_date,
    review_answer_timestamp::timestamp      as review_answer_timestamp,
    _ingested_at
from source
