with source as (

    select * from {{ source('olist','order_items') }}

)

select
    order_id,
    order_item_id::int                  as order_item_id,
    product_id,
    seller_id,
    shipping_limit_date::timestamp      as shipping_limit_date,
    price::numeric(10,2)                as price,
    freight_value::numeric(10,2)        as freight_value,
    _ingested_at
from source
