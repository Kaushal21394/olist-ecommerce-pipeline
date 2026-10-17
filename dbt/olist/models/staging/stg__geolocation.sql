-- raw, not deduped: many rows per zip prefix. Dedup lives in int_geolocation_deduped.
with source as (

    select * from {{ source('olist','geolocation') }}

)

select
    geolocation_zip_code_prefix::int    as geolocation_zip_code_prefix,
    geolocation_lat::numeric            as geolocation_lat,
    geolocation_lng::numeric            as geolocation_lng,
    geolocation_city,
    geolocation_state,
    _ingested_at
from source
