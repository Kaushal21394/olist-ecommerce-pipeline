"""The SQL safety layer: validate a query, then run it as the read-only agent role.

Used by the text-to-SQL graph (sql_tool.py) and the MCP server (rag/mcp_server).
It needs no model and no Anthropic key, so the MCP server can run it on its own.

Three layers:
  1. validate_sql() parses the query with sqlglot and allows only one SELECT
     that touches marts.* tables.
  2. run_sql() connects as the olist_agent_ro role (sql/006) with
     AGENT_DATABASE_URL, a read-only session, and a statement timeout.
  3. The role itself has SELECT on marts only, so the database enforces it
     even if the validator has a gap.
"""

import functools
import os
import re

import psycopg
import sqlglot
from sqlglot import exp

ALLOWED_SCHEMA = "marts"
# Models are told not to wrap SQL in markdown fences but sometimes do anyway.
FENCE_RE = re.compile(r"^```(?:sql)?\s*\n?(.*?)\n?```$", re.DOTALL)

# Column order follows attnum, which is the order dbt created the columns in.
SCHEMA_CARD_SQL = """
SELECT c.relname,
       obj_description(c.oid, 'pg_class'),
       a.attname,
       format_type(a.atttypid, a.atttypmod),
       col_description(c.oid, a.attnum)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname = %s AND c.relkind = 'r'
ORDER BY c.relname, a.attnum
"""
MAX_ROWS = 200
STATEMENT_TIMEOUT_MS = 10_000
# Belt and braces: the role can't call these anyway, but refuse them early with
# a clear message instead of a database permission error.
FORBIDDEN_FUNCTION_RE = re.compile(
    r"\b(pg_sleep\w*|pg_read_\w+|pg_ls_\w+|dblink\w*|lo_import|lo_export)\s*\(",
    re.IGNORECASE,
)

class UnsafeSQL(Exception):
    """The generated SQL was rejected before it reached the database."""


def connect_agent():
    """Open a read-only connection as the agent role (sql/006)."""
    conn = psycopg.connect(os.environ["AGENT_DATABASE_URL"])
    conn.read_only = True  # every transaction on this connection is read-only
    return conn


@functools.cache
def schema_card() -> str:
    """Describe the marts tables from the comments dbt persists (persist_docs).

    Tables, columns, types and descriptions are read from the database, so the
    agent sees what dbt last deployed. Cached for the life of the process.
    """
    conn = connect_agent()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_CARD_SQL, (ALLOWED_SCHEMA,))
            rows = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()

    lines = ["# marts schema card", "", "All tables live in the `marts` schema. Query them as `marts.<table>`.", ""]
    current = None
    for table, table_comment, column, col_type, col_comment in rows:
        if table != current:
            current = table
            lines += [f"## marts.{table}", "", " ".join((table_comment or "").split()), "",
                      "| column | type | description |", "|---|---|---|"]
        desc = " ".join((col_comment or "").split()).replace("|", "\\|")
        lines.append(f"| {column} | {col_type} | {desc} |")
    lines.append("")
    return "\n".join(lines)


def validate_sql(sql: str) -> str:
    """Return the cleaned SQL if it is one read-only SELECT over marts.*.

    Raises UnsafeSQL with a message the model can act on.
    """
    cleaned = sql.strip()
    fence_match = FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    cleaned = cleaned.rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQL("empty query")

    try:
        statements = sqlglot.parse(cleaned, read="postgres")
    except sqlglot.errors.ParseError as err:
        raise UnsafeSQL(f"query does not parse: {err}") from err

    if len(statements) != 1 or statements[0] is None:
        raise UnsafeSQL("expected exactly one statement")

    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise UnsafeSQL(f"only SELECT is allowed, got {type(tree).__name__}")

    # SELECT ... INTO creates a table and FOR UPDATE takes row locks.
    if tree.find(exp.Into) or tree.find(exp.Lock):
        raise UnsafeSQL("SELECT INTO and locking clauses are not allowed")

    cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not table.db and table.name in cte_names:
            continue
        if table.db != ALLOWED_SCHEMA:
            raise UnsafeSQL(
                f"table {table.sql()} is outside the {ALLOWED_SCHEMA} schema; "
                f"qualify tables as {ALLOWED_SCHEMA}.<table>"
            )

    match = FORBIDDEN_FUNCTION_RE.search(cleaned)
    if match:
        raise UnsafeSQL(f"function {match.group(1)} is not allowed")

    return cleaned


def run_sql(sql: str) -> tuple[list[str], list[tuple], bool]:
    """Run a validated query as the read-only agent role.

    Returns (column names, rows capped at MAX_ROWS, whether rows were truncated).
    """
    conn = connect_agent()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute(sql)
            columns = [col.name for col in cur.description]
            rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        return columns, rows[:MAX_ROWS], truncated
    finally:
        conn.rollback()
        conn.close()
