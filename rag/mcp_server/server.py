"""MCP server for the Olist data: lets Claude Desktop (or any MCP host) query the marts
and search review text.

The host model does the reasoning. It calls get_schema, writes a SQL query and calls
run_sql, or calls search_reviews. This server only validates and runs what it is given.
It calls no model, so it needs no Anthropic key. Every query runs under the read-only
agent role (sql/006), and every search uses the same filters as the router.

Tools:
  get_schema     the marts schema card, read from dbt's persisted descriptions
  run_sql        one validated read-only SELECT over marts.*
  search_reviews review text by meaning, with score, state, and late-delivery filters

Transport is stdio: the host starts this process and talks to it over stdin/stdout.
Nothing may print to stdout except the protocol. Logs go to stderr.

Claude Desktop config (~/Library/Application Support/Claude/claude_desktop_config.json):

    {
      "mcpServers": {
        "olist": {
          "command": "/Users/<you>/Projects/olist/.venv/bin/python",
          "args": ["/Users/<you>/Projects/olist/rag/mcp_server/server.py"]
        }
      }
    }

Credentials stay in the repo's .env, which this file loads by absolute path, so the
config file holds no secrets.

    python rag/mcp_server/server.py     # started by the host; run by hand only to debug
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")  # before the imports below read the environment

import psycopg  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

sys.path.insert(0, str(REPO / "rag" / "agent"))
import review_search_tool  # noqa: E402
import sql_guard  # noqa: E402
from review_search_tool import summarize_hits  # noqa: E402

mcp = FastMCP("olist", instructions=(
    "Olist Brazilian e-commerce data. Call get_schema before writing SQL. "
    "Use run_sql for numbers and search_reviews for what customers said."
))


@mcp.tool()
def get_schema() -> str:
    """Return the marts schema: every table and column, with types and descriptions.

    Call this before writing SQL. Every table is queried as marts.<table>.
    """
    return sql_guard.schema_card()


@mcp.tool()
def run_sql(sql: str) -> str:
    """Run one read-only SELECT over the marts tables and return the rows as JSON.

    Use for counts, totals, averages, rankings, and filters. Write exactly one SELECT
    (a WITH clause is fine), qualify every table as marts.<table>, and leave off the
    semicolon. Results are capped at 200 rows, and queries time out after 10 seconds.
    If the response contains an error, fix the query and try again.
    """
    try:
        clean = sql_guard.validate_sql(sql)
        columns, rows, truncated = sql_guard.run_sql(clean)
    except sql_guard.UnsafeSQL as err:
        return json.dumps({"error": f"rejected before running: {err}"})
    except psycopg.Error as err:
        return json.dumps({"error": f"database error: {err}"})
    return json.dumps({
        "sql": clean,
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }, ensure_ascii=False, default=str)


@mcp.tool()
def search_reviews(
    query: str,
    limit: int = 5,
    min_score: int | None = None,
    max_score: int | None = None,
    state: str | None = None,
    late: bool | None = None,
) -> str:
    """Find customer review texts about a topic, by meaning.

    Use when the answer depends on what customers said or why: complaints, praise, or a
    specific problem. The query can be Portuguese or English. Filters narrow the reviews
    first: min_score and max_score are 1-5, state is a 2-letter Brazilian code (e.g. "SP"),
    and late is true for late deliveries and false for on-time ones. Returns the closest
    reviews, best match first.
    """
    try:
        hits = review_search_tool.search_reviews(
            query, limit=limit, min_score=min_score, max_score=max_score, state=state, late=late,
        )
    except ValueError as err:
        return json.dumps({"error": str(err), "reviews": []})
    return json.dumps({"reviews": summarize_hits(hits)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()  # stdio transport
