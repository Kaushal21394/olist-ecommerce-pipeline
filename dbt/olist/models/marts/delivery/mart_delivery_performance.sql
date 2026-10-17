-- grain: one row per (purchase month, customer_state) — actual vs. estimated delivery,
-- late-delivery rate by state/period
with orders as (

    select * from {{ref('fct_orders')}}

)

, dim_date as (

    select * from {{ref('dim_date')}}

)

, orders_with_period as (

    select
        orders.*,
        dim_date.month_start    as purchase_month
    from orders
    left join dim_date
        on orders.order_purchase_timestamp::date = dim_date.date_day

)

select
    purchase_month,
    customer_state,
    count(*)                                                          as total_orders,
    count(*) filter (where order_delivered_customer_date is not null) as delivered_orders,
    count(*) filter (where is_late_delivery)                          as late_orders,
    round(
        100.0 * count(*) filter (where is_late_delivery)
        / nullif(count(*) filter (where order_delivered_customer_date is not null), 0)
    , 1)                                                               as late_delivery_rate_pct,
    round(avg(delivery_days), 1)                                       as avg_delivery_days,
    round(avg(delivery_days_vs_estimate), 1)                           as avg_delivery_days_vs_estimate
from orders_with_period
group by 1, 2
