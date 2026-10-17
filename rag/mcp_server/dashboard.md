# Monthly performance dashboard

A dashboard built in Claude Desktop from the olist server. Paste the prompt below into a new
chat with the server connected. Claude runs the analysis through `run_sql` and builds the
dashboard as an artifact.

## Prompt to paste

```
Using the olist data, build an interactive monthly performance dashboard as an artifact.

Data needed, by month from September 2016 to September 2018:
- number of orders
- total revenue in BRL
- average review score
- percentage of delivered orders that arrived late

Exclude canceled and unavailable orders. Month is the month the order was placed.

Dashboard requirements:
- Title: "Olist Monthly Performance, Sep 2016 to Sep 2018"
- Top row: four summary cards with total orders, total revenue (BRL), average review score,
  and average late-delivery percentage across the months.
- Chart 1: revenue as a line over time, with orders as bars on a second axis.
- Chart 2: average review score as a line over time.
- Chart 3: late-delivery percentage as a line over time.
- Treat September 2016 and September 2018 as low-volume months (1 to 2 orders) and leave
  them out of the summary card averages.
- Show the monthly numbers in a table below the charts.
- Format revenue as R$ with thousands separators.
```

## Reference query

Claude writes its own SQL from the prompt. This is the query the prompt is based on, which
you can use to check the numbers. It was run through the server's validator and returned
24 monthly rows.

```sql
SELECT date_trunc('month', order_purchase_timestamp)::date AS month,
       count(*) AS orders,
       round(sum(total_payment_value)::numeric, 2) AS revenue_brl,
       round(avg(review_score)::numeric, 2) AS avg_review_score,
       round(100.0 * avg(CASE WHEN is_late_delivery THEN 1 ELSE 0 END)
             FILTER (WHERE order_status = 'delivered'), 1) AS late_delivery_pct
FROM marts.fct_orders
WHERE order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1
ORDER BY 1
```

## Notes

- The first months have very few orders. September 2016 has 2 orders, and its late rate
  reads 100%. September 2018 has 1 order. Those months distort charts, so the prompt
  leaves them out of the summary averages.
- To drop low-volume months from the table as well, add `HAVING count(*) >= 100` after
  `GROUP BY 1`. This variant has not been run yet.
