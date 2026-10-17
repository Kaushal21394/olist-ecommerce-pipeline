-- grain: one row per (review_id, order_id) — every review with order context.
-- This is the table the Phase 5 embedding pipeline reads from.
with reviews as (

    select * from {{ref('stg__order_reviews')}}

)

, orders as (

    select * from {{ref('fct_orders')}}

)

select
    reviews.review_id,
    reviews.order_id,
    reviews.review_score,
    reviews.review_comment_title,
    reviews.review_comment_message,
    reviews.review_creation_date,
    reviews.review_answer_timestamp,
    date_part('day', reviews.review_answer_timestamp - reviews.review_creation_date)::int
                                                            as review_response_days,

    -- order context
    orders.order_status,
    orders.order_purchase_timestamp,
    orders.order_delivered_customer_date,
    orders.order_estimated_delivery_date,
    orders.is_late_delivery,
    orders.delivery_days,
    orders.total_payment_value,
    orders.customer_unique_id,
    orders.customer_city,
    orders.customer_state
from reviews
left join orders
    on reviews.order_id = orders.order_id
