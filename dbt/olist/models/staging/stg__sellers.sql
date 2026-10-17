with source as (

    select * from {{ source('olist','sellers') }}

)

select
    seller_id,
    seller_zip_code_prefix::int     as seller_zip_code_prefix,
    seller_city,
    seller_state,
    _ingested_at
from source
