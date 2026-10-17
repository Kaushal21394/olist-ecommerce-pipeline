-- grain: one row per customer_unique_id — RFM segmentation.
-- Recency/Frequency/Monetary are computed only from completed purchases (excludes
-- canceled/unavailable orders, which never converted into real revenue).
with orders as (

    select * from {{ref('fct_orders')}}
    where order_status not in ('canceled', 'unavailable')

)

, customers as (

    select * from {{ref('dim_customers')}}

)

, snapshot as (

    -- day after the most recent purchase in the dataset, so recency is always >= 1
    select max(order_purchase_timestamp)::date + interval '1 day' as snapshot_date
    from orders

)

, customer_orders as (

    select
        orders.customer_unique_id,
        max(orders.order_purchase_timestamp)          as last_order_date,
        count(distinct orders.order_id)                as frequency,
        sum(orders.total_payment_value)                as monetary
    from orders
    group by 1

)

, scored as (

    select
        customer_orders.*,
        date_part('day', snapshot.snapshot_date - customer_orders.last_order_date)::int   as recency_days,
        ntile(5) over (order by date_part('day', snapshot.snapshot_date - customer_orders.last_order_date) desc)
                                                                                           as recency_score,
        ntile(5) over (order by customer_orders.frequency asc)                            as frequency_score,
        ntile(5) over (order by customer_orders.monetary asc)                             as monetary_score
    from customer_orders
    cross join snapshot

)

select
    customers.customer_unique_id,
    customers.customer_city,
    customers.customer_state,
    scored.recency_days,
    scored.frequency,
    scored.monetary,
    scored.recency_score,
    scored.frequency_score,
    scored.monetary_score,
    (scored.recency_score + scored.frequency_score + scored.monetary_score)     as rfm_score,
    case
        when scored.recency_score >= 4 and scored.frequency_score >= 4 and scored.monetary_score >= 4 then 'champions'
        when scored.recency_score >= 4 and scored.frequency_score >= 3                                  then 'loyal_customers'
        when scored.recency_score >= 4                                                                  then 'recent_customers'
        when scored.recency_score <= 2 and scored.frequency_score >= 3                                  then 'at_risk'
        when scored.recency_score <= 2 and scored.frequency_score <= 2                                  then 'hibernating'
        else 'needs_attention'
    end                                                                          as rfm_segment
from scored
left join customers
    on scored.customer_unique_id = customers.customer_unique_id
