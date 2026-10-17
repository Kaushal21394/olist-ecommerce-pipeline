-- calendar spine covering the Olist order history (2016-09 to 2018-11)
with date_spine as (

    select generate_series('2016-01-01'::date, '2018-12-31'::date, interval '1 day')::date as date_day

)

select
    date_day,
    extract(year from date_day)::int            as year,
    extract(quarter from date_day)::int         as quarter,
    extract(month from date_day)::int           as month,
    trim(to_char(date_day, 'Month'))                as month_name,
    date_trunc('month', date_day)::date         as month_start,
    extract(week from date_day)::int            as iso_week,
    extract(isodow from date_day)::int          as day_of_week,
    trim(to_char(date_day, 'Day'))              as day_name,
    extract(isodow from date_day) in (6, 7)     as is_weekend
from date_spine
