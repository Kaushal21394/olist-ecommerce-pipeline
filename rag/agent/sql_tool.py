"""Text-to-SQL over marts.*: Claude writes SQL, we validate it, run it read-only.

The loop is a LangGraph graph: generate -> execute -> (retry on error) -> end.
Safety comes in three layers:
  1. validate_sql() parses the query with sqlglot and allows only one SELECT
     that touches marts.* tables.
  2. run_sql() connects as the olist_agent_ro role (sql/006) with
     AGENT_DATABASE_URL, a read-only session, and a statement timeout.
  3. The role itself has SELECT on marts only, so the database enforces it
     even if the validator has a gap.

    python rag/agent/sql_tool.py "How many delivered orders were late in SP?"
"""

import functools
import os
import sys
import uuid
from typing import TypedDict

import psycopg
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row

from sql_guard import MAX_ROWS, UnsafeSQL, run_sql, schema_card, validate_sql  # noqa: F401

load_dotenv()

MODEL = "claude-haiku-5-5"

MAX_SQL_ATTEMPTS = 2  # first try + one retry on a validation or SQL error

SYSTEM_PROMPT = """You write PostgreSQL queries against the marts schema of the Olist
e-commerce dataset. Rules:
- Use only tables and columns listed in the schema card.
- Qualify every table as marts.<table>.
- Return exactly one SELECT statement (a WITH clause is fine). No semicolons,
  no DDL or DML, no comments.
- Monetary values are in BRL. Follow the grain and filter notes in the card
  (for example, exclude canceled orders from revenue).
- If the question cannot be answered from the schema card, return only
  CANNOT_ANSWER.
Return only the SQL. No markdown fences and no explanation."""


llm = ChatAnthropic(model=MODEL, max_tokens=1024)  # reads ANTHROPIC_API_KEY


def build_user_message(question: str, previous_sql: str | None = None, error: str | None = None) -> str:
    content = f"<schema_card>\n{schema_card()}\n</schema_card>\n\nQuestion: {question}"
    if previous_sql and error:
        content += (
            f"\n\nYour previous query was:\n{previous_sql}\n\n"
            f"It failed with:\n{error}\n\nReturn a corrected query."
        )
    return content


def generate_sql(question: str, previous_sql: str | None = None, error: str | None = None) -> str:
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_user_message(question, previous_sql, error)),
    ])
    # Thinking blocks can come back before the answer. .text keeps only the text.
    return str(response.text).strip()


class SQLState(TypedDict):
    question: str
    sql: str | None
    error: str | None
    columns: list[str]
    rows: list[tuple]
    truncated: bool
    attempts: int


def _generate_node(state: SQLState) -> dict:
    sql = generate_sql(state["question"], state["sql"], state["error"])
    attempts = state["attempts"] + 1
    if sql == "CANNOT_ANSWER":
        return {"sql": None, "error": "question cannot be answered from the marts schema",
                "attempts": attempts}
    return {"sql": sql, "attempts": attempts}


def _execute_node(state: SQLState) -> dict:
    try:
        clean = validate_sql(state["sql"])
        columns, rows, truncated = run_sql(clean)
        return {"sql": clean, "columns": columns, "rows": rows,
                "truncated": truncated, "error": None}
    except (UnsafeSQL, psycopg.Error) as err:
        return {"error": str(err)}


def _after_generate(state: SQLState) -> str:
    return "end" if state["sql"] is None else "execute"


def _after_execute(state: SQLState) -> str:
    if state["error"] is None or state["attempts"] >= MAX_SQL_ATTEMPTS:
        return "end"
    return "generate"


@functools.cache
def _checkpoint_connection() -> psycopg.Connection:
    """Long-lived connection as olist_agent_state (sql/007), used only for checkpoints."""
    conn = psycopg.connect(
        os.environ["AGENT_CHECKPOINT_DATABASE_URL"],
        autocommit=True,  # the saver manages its own transactions
        row_factory=dict_row,  # required by PostgresSaver
    )
    saver = PostgresSaver(conn)
    saver.setup()  # creates LangGraph's checkpoint tables if they don't exist yet
    return conn


@functools.cache
def get_graph():
    """Compile the SQL graph with the Postgres checkpointer attached."""
    builder = StateGraph(SQLState)
    builder.add_node("generate", _generate_node)
    builder.add_node("execute", _execute_node)
    builder.add_edge(START, "generate")
    builder.add_conditional_edges("generate", _after_generate, {"execute": "execute", "end": END})
    builder.add_conditional_edges("execute", _after_execute, {"generate": "generate", "end": END})
    return builder.compile(checkpointer=PostgresSaver(_checkpoint_connection()))


def answer_sql_question(question: str, thread_id: str | None = None) -> dict:
    """Generate, validate and run SQL for a question, with one retry on error.

    Every step is checkpointed under thread_id. Pass the same thread_id later to
    read back the run with checkpoint_history().
    """
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    final = get_graph().invoke({
        "question": question, "sql": None, "error": None,
        "columns": [], "rows": [], "truncated": False, "attempts": 0,
    }, config)
    return {"thread_id": thread_id, "sql": final["sql"], "columns": final["columns"],
            "rows": final["rows"], "truncated": final["truncated"], "error": final["error"]}


def checkpoint_history(thread_id: str) -> list[dict]:
    """Every saved step of a run, oldest first: where it was, and what state it held."""
    config = {"configurable": {"thread_id": thread_id}}
    snapshots = list(reversed(list(get_graph().get_state_history(config))))  # oldest first
    steps = []
    for i, snap in enumerate(snapshots):
        # A snapshot records what runs *next*. The node that produced this step
        # is whatever the previous snapshot was about to run.
        node = "input" if i == 0 else ", ".join(snapshots[i - 1].next)
        steps.append({
            "step": snap.metadata.get("step"),
            "node": node,
            "next": list(snap.next),
            "sql": snap.values.get("sql"),
            "error": snap.values.get("error"),
            "attempts": snap.values.get("attempts"),
        })
    return steps


if __name__ == "__main__":
    result = answer_sql_question(" ".join(sys.argv[1:]))
    if result["error"]:
        print(f"error: {result['error']}")
    print(result["sql"] or "")
    if not result["error"]:
        print(" | ".join(result["columns"]))
        for row in result["rows"]:
            print(" | ".join(str(v) for v in row))
        if result["truncated"]:
            print(f"(truncated to {MAX_ROWS} rows)")
