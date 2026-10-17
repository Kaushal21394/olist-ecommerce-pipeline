-- Documented exception to the no-joins rule (TUTOR.md §3): the category translation is
-- joined here so every downstream model works in English.
with source as (

    select * from {{ source('olist','products') }}

)

, product_categories as (

    select * from {{ ref('stg__product_category') }}

)

select
    source.product_id,
    -- 2 categories have no translation; fall back to the Portuguese name
    coalesce(
        product_categories.product_category_name_english,
        source.product_category_name
    )                                                   as product_category_name,
    source.product_category_name                        as product_category_name_portuguese,
    source.product_name_lenght::int                     as product_name_length,
    source.product_description_lenght::int              as product_description_length,
    source.product_photos_qty::int                      as product_photos_qty,
    source.product_weight_g::int                        as product_weight_g,
    source.product_length_cm::int                       as product_length_cm,
    source.product_height_cm::int                       as product_height_cm,
    source.product_width_cm::int                        as product_width_cm,
    source._ingested_at
from source
left join product_categories
    on source.product_category_name = product_categories.product_category_name
