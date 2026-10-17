-- one row per order: payments are multi-row per order (vouchers, split payments)
with order_payments as (

    select * from {{ref('stg__order_payments')}}

)

select 
    order_id,
    count(*)                            as payment_count,
    count(distinct payment_type)        as payment_method_count,
    max(payment_installments)           as max_installments,
    sum(payment_value)                  as total_payment_value
from order_payments
group by 1
