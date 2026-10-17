"""Milestone 4b check: talk to the MCP server the way a host does, over stdio.

Starts server.py as a subprocess, lists its tools, and calls them. Each check
compares what the protocol returns against the same query run directly.

    python rag/mcp_server/mcp_test.py
"""

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "rag" / "mcp_server" / "server.py"
load_dotenv(REPO / ".env")
sys.path.insert(0, str(REPO / "rag" / "agent"))
import sql_guard  # noqa: E402  (used only to compare against a direct run)
EXPECTED_TOOLS = {"get_schema", "run_sql", "search_reviews"}


def text_of(result) -> str:
    return "".join(block.text for block in result.content if block.type == "text")


async def call(session, name: str, args: dict):
    return text_of(await session.call_tool(name, args))


async def run_checks() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    failures = 0
    total = 0

    def report(ok: bool, name: str, detail: str = "") -> None:
        nonlocal failures, total
        total += 1
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = {t.name for t in (await session.list_tools()).tools}
            report(tools == EXPECTED_TOOLS, "tools listed", ", ".join(sorted(tools)))

            schema = await call(session, "get_schema", {})
            report("## marts.fct_orders" in schema, "get_schema returns the schema card",
                   f"{schema.count('## marts.')} tables")

            count_sql = "SELECT count(*) AS orders FROM marts.fct_orders"
            got = json.loads(await call(session, "run_sql", {"sql": count_sql}))
            _, direct_rows, _ = sql_guard.run_sql(count_sql)
            report(got.get("rows") == [list(r) for r in direct_rows] and got.get("row_count") == 1,
                   "run_sql matches a direct run", f"orders={got.get('rows')}")

            rejected = [
                ("DELETE rejected", "DELETE FROM marts.fct_orders"),
                ("table outside marts rejected", "SELECT * FROM public.review_embeddings"),
                ("two statements rejected", "SELECT 1; SELECT 2"),
                ("pg_sleep rejected", "SELECT pg_sleep(5)"),
            ]
            for name, sql in rejected:
                out = json.loads(await call(session, "run_sql", {"sql": sql}))
                report("error" in out and "rows" not in out, name, out.get("error", "")[:80])

            hits = json.loads(await call(session, "search_reviews", {
                "query": "entrega atrasada", "limit": 5, "max_score": 2, "state": "SP", "late": True,
            }))["reviews"]
            ok = len(hits) == 5 and all(
                h["review_score"] <= 2 and h["customer_state"] == "SP" and h["is_late_delivery"] is True
                for h in hits
            )
            report(ok, "search_reviews keeps filters and fills the limit", f"{len(hits)} rows")

            bad = json.loads(await call(session, "search_reviews", {"query": "teste", "min_score": 9}))
            report("error" in bad, "invalid filter returns an error, not a crash")

    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_checks()))
