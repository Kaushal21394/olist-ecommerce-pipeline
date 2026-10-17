-- multiple rows per order (one per payment_sequential); aggregated in int_order_payments_agg.
with source as (

    select * from {{ source('olist','order_payments') }}

)

select
    order_id,
    payment_sequential::int         as payment_sequential,
    payment_type,
    payment_installments::int       as payment_installments,
    payment_value::numeric(10,2)    as payment_value,
    _ingested_at
from source
