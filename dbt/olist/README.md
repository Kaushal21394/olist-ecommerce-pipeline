# olist — dbt project

This is the dbt project for the [Olist data platform](../../README.md). It transforms the raw Olist e-commerce CSVs, landed in Postgres by the ingestion scripts, into a tested, documented star schema plus subject-area marts. See [LINEAGE.md](LINEAGE.md) for the full model DAG. This README covers what's specific to running and extending the dbt project itself.

## Setup

- dbt Core 1.12.x with the `dbt-postgres` adapter.
- A `profiles.yml` entry named `olist` pointing at the `olist_db` Postgres database (see `dbt_project.yml`'s `profile:` key). The `dev` target reads from schema `staging` by default — that's where `bronze` sources already live and where staging/intermediate models are built; `marts` models are built into their own `marts` schema regardless of the target schema (see [Schemas](#schemas) below).
- The bronze tables must already exist and be loaded (`sql/001_schemas_and_extensions.sql` + `sql/002_bronze_batch_tables.sql`, then the batch ingestion script). This project only reads from `bronze` via `models/staging/_sources.yml`; it never loads data itself.

```bash
dbt debug        # confirm the connection works
dbt build         # run + test everything
dbt build --select staging       # just the staging layer
dbt build --select marts.core    # just the star schema
dbt docs generate && dbt docs serve   # browse the generated docs site
```

## Layers

Medallion mapping: `bronze` (raw Postgres tables, outside dbt) → `staging`/`intermediate` (silver) → `marts` (gold).

| Layer | Path | Materialization | Schema | Convention |
|---|---|---|---|---|
| Staging | `models/staging/` | view | `staging` | 1:1 with a bronze source table. Casts/renames/cleans only — no joins, with one documented exception (see below). |
| Intermediate | `models/intermediate/` | view | `staging` | Joins/aggregation that reshapes staging-grain data before it can join cleanly into a fact/dim at the right grain. Not a reporting-ready shape. |
| Marts — core | `models/marts/core/` | table | `marts` | The dimensional star schema: `dim_customers`, `dim_sellers`, `dim_products`, `dim_date`, `fct_orders`, `fct_order_items`. |
| Marts — subject | `models/marts/<subject>/` | table | `marts` | One folder per subject area (`delivery/`, `seller/`, `customers/`, `reviews/`), each answering a specific reporting question on top of core. |

**The one intentional exception to "staging has no joins":** `stg__products` joins the category-translation lookup (`stg__product_category`) so every downstream model gets English category names, instead of every consumer having to join the translation itself. This is documented inline in the model.

### Staging → intermediate → marts, as built

```
stg__customers ─────────────┐
stg__orders ─────────────┐  ├─► dim_customers ─┐
int__geolocation_deduped ─┤  │                  ├─► fct_orders ─┬─► mart_delivery_performance
stg__geolocation ─────────┘  │                  │                ├─► mart_customer_rfm
stg__sellers ────────────────┼─► dim_sellers ───┘                ├─► mart_review_base
stg__order_payments ─► int__order_payments_agg ─┴─────────────────┘
stg__order_reviews ──► int__order_reviews_agg ──┘
stg__product_category ─► stg__products ─► dim_products ─┐
stg__order_items ────────────────────────────────────────┴─► fct_order_items ─► mart_seller_performance
```

`dim_date` is a generated calendar spine (2016-01-01 to 2018-12-31, via `generate_series`), not sourced from a bronze table.

**Not built — parked:** a streaming staging model and an order-status SCD2 snapshot, both depending on streaming/CDC bronze tables that don't exist, since the source dataset is static. See [LINEAGE.md](LINEAGE.md).

## Schemas

Custom `generate_schema_name` macro (`macros/generate_schema_name.sql`) makes a model's `+schema` config the *literal* schema name, instead of dbt's default `<target_schema>_<custom_schema>` concatenation. So `+schema: marts` in `dbt_project.yml` puts every marts model in a schema called exactly `marts`, no matter what the target's default schema is. Models with no custom schema (staging, intermediate) fall back to the target schema (`staging` in `dev`).

## Grain gotchas

A few places where the natural-looking key isn't actually unique, or the doc's assumed grain needed adjusting once checked against the data — worth knowing before writing a new model against these:

- **`customer_id` vs `customer_unique_id`**: `customer_id` is issued per order; `customer_unique_id` is the real person. `dim_customers` is keyed on `customer_unique_id`. Anything joining an order to `dim_customers` has to go `stg__orders.customer_id` → `stg__customers.customer_unique_id` → `dim_customers`, not straight from `customer_id`.
- **`stg__order_reviews`**: `review_id` alone isn't unique — the same review can be attached to more than one `order_id`. The real grain is (`review_id`, `order_id`). `int__order_reviews_agg` collapses this to one row per `order_id` (latest review by answer timestamp) for `fct_orders`; `mart_review_base` keeps every review, unaggregated, for the review-analysis pipeline.
- **`stg__order_payments`**: multi-row per order (installments, split payment methods). `int__order_payments_agg` collapses to one row per `order_id`.
- **`stg__geolocation`**: many rows per zip-code prefix, some with GPS noise outside Brazil's bounding box. `int__geolocation_deduped` filters those out and averages the rest to one row per prefix.
- **8 orders are marked `order_status = 'delivered'` with no `order_delivered_customer_date`** — a known gap in the source data, not an ingestion bug. Anything computing delivery time should filter on the date being non-null, not on status.

## Testing

Every model has at least `unique` + `not_null` on its grain key; foreign keys in the marts layer carry `relationships` tests back to their dimension. Run `dbt build` (not just `dbt run`) to get tests alongside builds. `dbt build --select <model>+` tests a model and everything downstream of it.

## Documentation

Every marts-layer model and column has a `description` in its adjacent `_*.yml` file (e.g. `models/marts/core/_core_facts.yml`), written for exactly the kind of nuance in [Grain gotchas](#grain-gotchas) above — null semantics, which key to join on, what an aggregate does and doesn't include. `+persist_docs` is enabled for the `marts` schema, so these descriptions are also written as real Postgres `COMMENT ON TABLE`/`COMMENT ON COLUMN` statements on every build — readable straight from `information_schema` by anything querying the warehouse (including the RAG/agent layer), not just from the dbt docs site.

## Resources

- [dbt docs](https://docs.getdbt.com/docs/introduction)
- [dbt-postgres adapter docs](https://docs.getdbt.com/reference/warehouse-setups/postgres-setup)
