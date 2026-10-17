-- one row per zip prefix: average of the in-Brazil coordinates, most common city/state
with geolocation as (

    select * from {{ref('stg__geolocation')}}

)

select
    geolocation_zip_code_prefix,
    avg(geolocation_lat)                                        as geolocation_lat,
    avg(geolocation_lng)                                        as geolocation_lng,
    mode() within group (order by geolocation_city)             as geolocation_city,
    mode() within group (order by geolocation_state)            as geolocation_state
from geolocation
-- a few dozen points fall outside Brazil's bounding box and would skew the average
where geolocation_lat between -34 and 5.5
  and geolocation_lng between -74 and -34
group by 1
