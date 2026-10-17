-- grain: one row per order_id
with orders as (

    select * from {{ref('stg__orders')}}

)

, customers as (

    select * from {{ref('stg__customers')}}

)

, payments as (

    select * from {{ref('int__order_payments_agg')}}

)

, reviews as (

    select * from {{ref('int__order_reviews_agg')}}

)

, dim_customers as (

    select * from {{ref('dim_customers')}}

)

select
    orders.order_id,
    customers.customer_unique_id,
    orders.customer_id,
    orders.order_status,
    orders.order_purchase_timestamp,
    orders.order_approved_at,
    orders.order_delivered_carrier_date,
    orders.order_delivered_customer_date,
    orders.order_estimated_delivery_date,

    -- delivery performance
    (orders.order_delivered_customer_date > orders.order_estimated_delivery_date)  as is_late_delivery,
    date_part('day', orders.order_delivered_customer_date - orders.order_purchase_timestamp)::int
                                                                                     as delivery_days,
    date_part('day', orders.order_delivered_customer_date - orders.order_estimated_delivery_date)::int
                                                                                     as delivery_days_vs_estimate,

    -- payments
    payments.payment_count,
    payments.payment_method_count,
    payments.max_installments,
    payments.total_payment_value,

    -- reviews
    reviews.review_id,
    reviews.review_score,
    reviews.review_creation_date,
    reviews.review_answer_timestamp,
    reviews.review_count,

    -- customer geo, denormalized for convenience
    dim_customers.customer_city,
    dim_customers.customer_state
from orders
left join customers
    on orders.customer_id = customers.customer_id
left join dim_customers
    on customers.customer_unique_id = dim_customers.customer_unique_id
left join payments
    on orders.order_id = payments.order_id
left join reviews
    on orders.order_id = reviews.order_id
