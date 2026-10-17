#!/usr/bin/env python3
"""
Batch loader: Olist source CSVs -> bronze schema (Postgres).

Usage:
    python load_bronze.py --data-dir ../../data/raw
    python load_bronze.py --data-dir ../../data/raw --tables customers,orders
    python load_bronze.py --data-dir ../../data/raw --no-truncate

Design notes:
  - Bronze columns are all TEXT. This loader never casts or validates field
    values — a malformed row should never block a load. Typing happens in
    dbt staging models.
  - Each table load is a full-refresh (TRUNCATE + COPY) by default, since
    this is the one-time historical batch load, not an incremental append.
    Pass --no-truncate to append instead (e.g. when re-running against a
    table you're intentionally accumulating).
  - Rows are streamed into Postgres via COPY rather than buffered INSERTs —
    COPY is the fastest bulk-load path in Postgres, and streaming (rather
    than materializing the augmented CSV in memory) keeps memory flat even
    for the ~1M-row geolocation file.
  - The CSV header is validated against the expected column order before
    any data is loaded. This is a boundary check: these files come from an
    external download (Kaggle), and a mismatched export should fail loudly
    and early rather than silently loading garbage.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import psycopg

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# -----------------------------------------------------------------------------
# Table configuration — CSV filename + column order, matching sql/002_bronze_batch_tables.sql
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class TableConfig:
    bronze_table: str
    csv_filename: str
    columns: tuple[str, ...]


TABLE_CONFIGS: tuple[TableConfig, ...] = (
    TableConfig(
        bronze_table="customers",
        csv_filename="olist_customers_dataset.csv",
        columns=(
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ),
    ),
    TableConfig(
        bronze_table="geolocation",
        csv_filename="olist_geolocation_dataset.csv",
        columns=(
            "geolocation_zip_code_prefix",
            "geolocation_lat",
            "geolocation_lng",
            "geolocation_city",
            "geolocation_state",
        ),
    ),
    TableConfig(
        bronze_table="orders",
        csv_filename="olist_orders_dataset.csv",
        columns=(
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ),
    ),
    TableConfig(
        bronze_table="order_items",
        csv_filename="olist_order_items_dataset.csv",
        columns=(
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ),
    ),
    TableConfig(
        bronze_table="order_payments",
        csv_filename="olist_order_payments_dataset.csv",
        columns=(
            "order_id",
            "payment_sequential",
            "payment_type",
            "payment_installments",
            "payment_value",
        ),
    ),
    TableConfig(
        bronze_table="order_reviews",
        csv_filename="olist_order_reviews_dataset.csv",
        columns=(
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ),
    ),
    TableConfig(
        bronze_table="products",
        csv_filename="olist_products_dataset.csv",
        columns=(
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ),
    ),
    TableConfig(
        bronze_table="sellers",
        csv_filename="olist_sellers_dataset.csv",
        columns=(
            "seller_id",
            "seller_zip_code_prefix",
            "seller_city",
            "seller_state",
        ),
    ),
    TableConfig(
        bronze_table="product_category_name_translation",
        csv_filename="product_category_name_translation.csv",
        columns=(
            "product_category_name",
            "product_category_name_english",
        ),
    ),
)


# -----------------------------------------------------------------------------
# Streaming CSV -> COPY
# -----------------------------------------------------------------------------


def augmented_row_chunks(csv_path: Path, source_file: str, batch_id: str, encoding: str):
    """Yields the source CSV re-encoded with _source_file and _batch_id appended
    to every row, one encoded line at a time. _ingested_at is intentionally
    left out — it uses the column's DEFAULT now() in Postgres.
    """
    with open(csv_path, newline="", encoding=encoding) as f:
        reader = csv.reader(f)
        next(reader)  # header, already validated by caller

        out_buffer = io.StringIO()
        writer = csv.writer(out_buffer)

        for row in reader:
            writer.writerow([*row, source_file, batch_id])
            yield out_buffer.getvalue().encode("utf-8")
            out_buffer.seek(0)
            out_buffer.truncate(0)


def validate_header(csv_path: Path, expected_columns: tuple[str, ...], encoding: str) -> None:
    with open(csv_path, newline="", encoding=encoding) as f:
        header = next(csv.reader(f))
    if tuple(header) != expected_columns:
        raise ValueError(
            f"{csv_path.name}: header does not match expected columns.\n"
            f"  expected: {expected_columns}\n"
            f"  found:    {tuple(header)}"
        )


# -----------------------------------------------------------------------------
# Load logic
# -----------------------------------------------------------------------------


def get_connection():
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return psycopg.connect(dsn)
    try:
        password = os.environ["PGPASSWORD"]
    except KeyError:
        raise RuntimeError(
            "Set DATABASE_URL, or PGPASSWORD plus the other PG* vars, in .env."
        ) from None
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "olist_db"),
        user=os.environ.get("PGUSER", "postgres"),
        password=password,
    )


def load_table(conn, data_dir: Path, config: TableConfig, batch_id: str, truncate: bool, encoding: str) -> int:
    csv_path = data_dir / config.csv_filename
    if not csv_path.exists():
        raise FileNotFoundError(f"expected CSV not found: {csv_path}")

    validate_header(csv_path, config.columns, encoding)

    copy_columns = [*config.columns, "_source_file", "_batch_id"]
    copy_sql = (
        f"COPY bronze.{config.bronze_table} ({', '.join(copy_columns)}) "
        f"FROM STDIN WITH (FORMAT csv)"
    )

    with conn.cursor() as cur:
        if truncate:
            cur.execute(f"TRUNCATE TABLE bronze.{config.bronze_table}")

        chunks = augmented_row_chunks(csv_path, config.csv_filename, batch_id, encoding)
        # Stream chunks straight into Postgres; the augmented CSV is never held in memory.
        with cur.copy(copy_sql) as copy:
            for chunk in chunks:
                copy.write(chunk)
        row_count = cur.rowcount

    conn.commit()
    return row_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"), help="directory containing the Olist CSVs")
    parser.add_argument("--tables", type=str, default=None, help="comma-separated subset of bronze table names to load (default: all)")
    parser.add_argument("--batch-id", type=str, default=None, help="override the generated batch id")
    parser.add_argument(
        "--encoding",
        type=str,
        default="utf-8-sig",
        help="CSV file encoding (utf-8-sig strips a UTF-8 BOM if present, and is a no-op if not — some Olist CSV exports carry one)",
    )
    truncate_group = parser.add_mutually_exclusive_group()
    truncate_group.add_argument("--truncate", dest="truncate", action="store_true", help="TRUNCATE each bronze table before loading (default)")
    truncate_group.add_argument("--no-truncate", dest="truncate", action="store_false", help="append instead of truncating")
    parser.set_defaults(truncate=True)
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"error: data dir not found: {args.data_dir}", file=sys.stderr)
        return 1

    selected_tables = set(args.tables.split(",")) if args.tables else None
    configs = [c for c in TABLE_CONFIGS if selected_tables is None or c.bronze_table in selected_tables]
    if selected_tables and len(configs) != len(selected_tables):
        found = {c.bronze_table for c in configs}
        print(f"error: unknown table(s): {selected_tables - found}", file=sys.stderr)
        return 1

    batch_id = args.batch_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}Z-{uuid.uuid4().hex[:8]}"
    print(f"batch_id: {batch_id}  mode: {'truncate+load' if args.truncate else 'append'}")

    conn = get_connection()
    failures = []
    try:
        for config in configs:
            start = time.monotonic()
            try:
                row_count = load_table(conn, args.data_dir, config, batch_id, args.truncate, args.encoding)
                elapsed = time.monotonic() - start
                print(f"  bronze.{config.bronze_table:<38} {row_count:>8} rows  ({elapsed:.1f}s)")
            except Exception as exc:  # noqa: BLE001 — surface per-table failure, keep going
                conn.rollback()
                failures.append((config.bronze_table, exc))
                print(f"  bronze.{config.bronze_table:<38} FAILED: {exc}", file=sys.stderr)
    finally:
        conn.close()

    if failures:
        print(f"\n{len(failures)} table(s) failed to load", file=sys.stderr)
        return 1

    print("\nall tables loaded successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
