with sellers as (

    select * from {{ref('stg__sellers')}}

)

, geolocation as (

    select * from {{ref('int__geolocation_deduped')}}

)

select
    sellers.seller_id,
    sellers.seller_zip_code_prefix,
    sellers.seller_city,
    sellers.seller_state,
    geolocation.geolocation_lat         as seller_lat,
    geolocation.geolocation_lng         as seller_lng
from sellers
left join geolocation
    on sellers.seller_zip_code_prefix = geolocation.geolocation_zip_code_prefix
