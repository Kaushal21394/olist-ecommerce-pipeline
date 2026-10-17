-- grain: one row per customer_unique_id (the real person). customer_id is per-order in Olist,
-- so a repeat buyer has several. Address is taken from their most recent order.
with customers as (

    select * from {{ref('stg__customers')}}

)

, orders as (

    select * from {{ref('stg__orders')}}

)

, geolocation as (

    select * from {{ref('int__geolocation_deduped')}}

)

, latest_address as (

    select
        customers.*,
        count(*) over (partition by customers.customer_unique_id) as customer_id_count,
        row_number() over (
            partition by customers.customer_unique_id
            order by orders.order_purchase_timestamp desc, customers.customer_id
        ) as address_rank
    from customers
    left join orders
        on customers.customer_id = orders.customer_id

)

select
    latest_address.customer_unique_id,
    latest_address.customer_zip_code_prefix,
    latest_address.customer_city,
    latest_address.customer_state,
    geolocation.geolocation_lat         as customer_lat,
    geolocation.geolocation_lng         as customer_lng,
    latest_address.customer_id_count
from latest_address
left join geolocation
    on latest_address.customer_zip_code_prefix = geolocation.geolocation_zip_code_prefix
where latest_address.address_rank = 1
