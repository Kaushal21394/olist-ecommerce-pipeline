-- grain: one row per (order_id, order_item_id) — the line-item level
with order_items as (

    select * from {{ref('stg__order_items')}}

)

, orders as (

    select * from {{ref('fct_orders')}}

)

select
    order_items.order_id,
    order_items.order_item_id,
    order_items.product_id,
    order_items.seller_id,
    orders.customer_unique_id,
    order_items.shipping_limit_date,
    order_items.price,
    order_items.freight_value,
    order_items.price + order_items.freight_value      as item_total_value,
    orders.order_status,
    orders.order_purchase_timestamp,
    orders.is_late_delivery
from order_items
inner join orders
    on order_items.order_id = orders.order_id
