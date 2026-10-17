-- grain: one row per seller_id — revenue, order count, avg delivery time per seller
with order_items as (

    select * from {{ref('fct_order_items')}}

)

, sellers as (

    select * from {{ref('dim_sellers')}}

)

, seller_orders as (

    -- one row per order item (fct_order_items grain); delivery_days is pulled in from
    -- fct_orders (order grain) via a plain many-to-one left join, no aggregation here
    select
        order_items.order_id,
        order_items.order_item_id,
        order_items.seller_id,
        order_items.item_total_value,
        order_items.is_late_delivery,
        fct_orders.delivery_days
    from order_items
    left join {{ref('fct_orders')}} as fct_orders
        on order_items.order_id = fct_orders.order_id

)

select
    sellers.seller_id,
    sellers.seller_city,
    sellers.seller_state,
    count(distinct seller_orders.order_id)                     as order_count,
    count(*)                                                    as item_count,
    sum(seller_orders.item_total_value)                         as total_revenue,
    round(avg(seller_orders.item_total_value), 2)               as avg_item_value,
    round(avg(seller_orders.delivery_days), 1)                  as avg_delivery_days,
    count(*) filter (where seller_orders.is_late_delivery)      as late_order_items,
    round(
        100.0 * count(*) filter (where seller_orders.is_late_delivery) / nullif(count(*), 0)
    , 1)                                                         as late_rate_pct
from seller_orders
left join sellers
    on seller_orders.seller_id = sellers.seller_id
group by 1, 2, 3
