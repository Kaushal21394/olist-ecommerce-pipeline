# Olist Data Platform

An end-to-end data platform built on the [Olist Brazilian e-commerce public
dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce): a medallion
warehouse in Postgres, built with dbt, topped with a retrieval-augmented agent that
answers natural-language questions over the data — by text-to-SQL, by semantic search
over review text, or both.

## What's here

- **A dbt-built warehouse** (bronze → silver → gold) over the ~100k-order Olist dataset:
  a dimensional star schema plus subject-area marts for delivery performance, seller
  performance, customer RFM segmentation, and review analysis.
- **A review-embedding store** in `pgvector`, so review text is searchable by meaning,
  not just keyword.
- **A router agent** (LangGraph + Claude) that decides, per question, whether to query
  the warehouse, search reviews, or both, and answers from whatever it gets back.
- **An MCP server** exposing the same schema and tools to Claude Desktop, so the warehouse
  can be queried conversationally without any custom front end.
- **An evaluation harness** that scores the agent against a hand-written golden set of
  questions and expected SQL results.

## Architecture

```
                     ┌───────────────────────────────┐
                     │      Olist CSVs (historical)    │
                     └───────────────┬─────────────────┘
                                      │  batch load
                                      ▼
     ┌─────────────────────────────────────────────────────────────┐
     │  BRONZE  (Postgres schema: bronze)                            │
     │  raw, immutable, append-only landing tables                   │
     └───────────────────────────────┬───────────────────────────────┘
                                      │  dbt staging + intermediate
                                      ▼
     ┌─────────────────────────────────────────────────────────────┐
     │  SILVER  (dbt: staging + intermediate)                        │
     │  cleaned, typed, deduplicated, conformed                      │
     └───────────────────────────────┬───────────────────────────────┘
                                      │  dbt marts
                                      ▼
     ┌─────────────────────────────────────────────────────────────┐
     │  GOLD  (dbt: marts)                                           │
     │  star schema (fct_orders, dim_customers, dim_products, ...)   │
     │  + subject marts (delivery, seller, RFM, reviews)             │
     └───────────────────────────────┬───────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                     ▼
         ┌───────────────────────┐            ┌───────────────────────────┐
         │  pgvector embeddings   │            │   Router agent             │
         │  (review text)          │◄───────────┤   text-to-SQL over gold    │
         │                         │            │   semantic search over     │
         │                         │            │   review embeddings        │
         └───────────────────────┘            └──────────────┬─────────────┘
                                                                │
                                                       ┌────────┴────────┐
                                                       ▼                 ▼
                                                 CLI / notebook     MCP server
                                                                    (Claude Desktop)
```

Streaming ingestion (Kafka/Redpanda) and CDC (Debezium on Postgres logical replication)
were designed and scoped for this project but are **deliberately parked**: the dataset is
static and historical, so there's no live source to stream or capture changes from. The
schema for both still exists (`sql/003`, `sql/004`), kept as a reference.

## Tech stack

| Layer | Tool | Why |
|---|---|---|
| Database | PostgreSQL + `pgvector` | One backend for the warehouse *and* the vector store |
| Transformations | dbt-postgres | Staging/intermediate/marts layering, tests, docs, `persist_docs` |
| Ingestion | Python + `psycopg` | Batch CSV loader into bronze, streamed via `COPY` |
| Embeddings | `sentence-transformers` (`paraphrase-multilingual-mpnet-base-v2`) | Local, free, handles Portuguese review text natively |
| Agent orchestration | LangGraph + LangChain (`ChatAnthropic`) | Durable, checkpointed tool-use loop |
| SQL safety | `sqlglot` | Parses and validates every generated query before it runs, read-only |
| Agent exposure | MCP (`mcp` / FastMCP) | Lets Claude Desktop use the same tools over stdio, no custom UI needed |

## Project structure

```
olist/
├── sql/                     # numbered Postgres migrations: schemas, roles, grants
├── ingestion/
│   └── batch/                 # historical CSV loader -> bronze schema
├── dbt/
│   └── olist/                 # dbt project: staging -> intermediate -> marts
│       ├── README.md          # dbt-specific setup, layers, grain gotchas
│       └── LINEAGE.md         # full model DAG
├── rag/
│   ├── agent/                  # text-to-SQL tool, review-search tool, router agent
│   ├── evaluation/             # golden-set eval harness
│   └── mcp_server/             # MCP server + setup guide for Claude Desktop
├── dashboard/                  # example dashboard built through the MCP server
├── data/raw/                   # Olist CSVs (gitignored — see Data source below)
└── deployment.md                # moving this from a laptop to a cloud environment
```

## Data source

[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
— about 100k orders from 2016–2018, across order items, payments, reviews, customers,
sellers, products, and geolocation, in 9 relational CSVs. Download it from Kaggle into
`data/raw/` (not committed — see `.gitignore`).

## Getting started

1. A local PostgreSQL 16+ instance with the `pgvector` extension available.
2. Copy `ingestion/batch/.env.example` to `.env` in the repo root and fill in your database
   connection details, plus `ANTHROPIC_API_KEY` for the agent.
3. `pip install -r requirements.txt`
4. Apply the migrations in order: `for f in sql/0*.sql; do psql "$DATABASE_URL" -f "$f"; done`
5. Download the dataset from Kaggle into `data/raw/`, then run the batch loader:
   `python ingestion/batch/load_bronze.py`
6. Build the warehouse: `cd dbt/olist && dbt build`
7. Embed the reviews into `vector.review_embeddings` (see `dbt/olist/LINEAGE.md` for where
   `mart_review_base` comes from).
8. Ask a question: `python rag/agent/router.py "Which states have the most late deliveries?"`,
   or connect the MCP server to Claude Desktop (`rag/mcp_server/README.md`).

## Status

The warehouse (bronze/silver/gold) and the RAG + agent layer are built and evaluated —
see `dbt/olist/README.md` and `rag/mcp_server/README.md` for each piece. Not yet built: a
web front end for the agent, and a remote (authenticated) MCP endpoint.

## License / attribution

Dataset provided by Olist under its Kaggle license terms. Built by Kaushal Chaudhary, for
personal, educational use.
