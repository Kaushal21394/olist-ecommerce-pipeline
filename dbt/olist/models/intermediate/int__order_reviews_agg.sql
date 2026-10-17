-- one row per order: keep the latest review when an order has several
with order_reviews as (

    select * from {{ref('stg__order_reviews')}}

)

, ranked as (

    select
        *,
        row_number() over (
            partition by order_id
            order by review_answer_timestamp desc, review_creation_date desc, review_id
        )                                               as review_rank,
        count(*) over (partition by order_id)           as review_count
    from order_reviews

)

select
    order_id,
    review_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp,
    review_count
from ranked
where review_rank = 1
