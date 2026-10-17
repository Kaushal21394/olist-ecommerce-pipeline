"""Router agent: one model that decides, for each question, whether to query the
numbers, search the reviews, or both, then answers from what the tools returned.

The graph is a loop: the model node may ask for tools, the tools node runs them,
and control returns to the model until it answers without a tool call. Every step
is saved by the Postgres checkpointer under a thread_id, so a conversation can
be resumed or inspected later.

    python rag/agent/router.py
"""

import argparse
import functools
import os
import sys
import uuid
from typing import Annotated, TypedDict

import psycopg
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from psycopg.rows import dict_row

from sql_tool import MODEL
from tools import TOOLS

MAX_STEPS = 8  # model turns per question; a runaway loop stops here

SYSTEM_PROMPT = """You answer questions about Brazilian e-commerce orders (Olist) using two tools.

- query_sql: numbers. Counts, totals, averages, rankings, and filters over orders,
  sellers, products, customers, payments, and reviews as numbers.
- search_reviews: text. What customers said or why: complaints, praise, specific problems.

Choose the tools by what the question needs:
- Numbers only: query_sql.
- What customers said or why, with no numbers: search_reviews.
- Both (e.g. "how many late deliveries got one-star reviews, and what did they say"):
  call both, then answer from both.
- A follow-up with a count, total, or ranking word ("how many", "out of those", "what
  percent") ALWAYS needs a fresh query_sql call, even if a search_reviews result is still
  in context and looks countable. search_reviews returns at most a handful of reviews out
  of thousands; tallying its sample instead of querying the full table will give a wrong
  number that looks plausible. The only time you answer straight from a prior tool result
  without a new call is when the follow-up asks about those specific returned items (e.g.
  "which of those was from São Paulo?", "quote the angriest one").

Rules:
- Answer only from tool results. If a tool returns an error or no rows, say so.
  Do not guess a number.
- Quote review text briefly, and say how many reviews you read.
- Reply in the language the user wrote in: English for English, Portuguese for Portuguese.
  Review text is in Portuguese, but that does not change the reply language.
- Keep the answer short. Use a small table only for three or more rows of numbers.
"""


class RouterState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


@functools.cache
def _model():
    # ChatAnthropic reads ANTHROPIC_API_KEY. bind_tools advertises the tool schemas.
    return ChatAnthropic(model=MODEL, max_tokens=2048).bind_tools(TOOLS)


def call_model(state: RouterState) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = _model().invoke(messages)
    return {"messages": [response]}


def _after_model(state: RouterState) -> str:
    # Stop when the model has answered, or when the model turns reach MAX_STEPS.
    model_turns = sum(1 for m in state["messages"] if isinstance(m, AIMessage))
    if model_turns >= MAX_STEPS:
        return END
    return tools_condition(state)


@functools.cache
def _checkpoint_connection() -> psycopg.Connection:
    # Own connection, not sql_tool's. The SQL graph runs inside a tool call, so
    # sharing one connection would nest two checkpointer operations on it.
    return psycopg.connect(
        os.environ["AGENT_CHECKPOINT_DATABASE_URL"], autocommit=True, row_factory=dict_row,
    )


@functools.cache
def get_graph():
    builder = StateGraph(RouterState)
    builder.add_node("model", call_model)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", _after_model, {"tools": "tools", END: END})
    builder.add_edge("tools", "model")

    checkpointer = PostgresSaver(_checkpoint_connection())
    checkpointer.setup()  # idempotent: creates the checkpoint tables if missing
    return builder.compile(checkpointer=checkpointer)


def _steps(messages: list[AnyMessage]) -> list[dict]:
    """Turn the new messages of one run into a readable trace: tool calls and their results."""
    steps = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                steps.append({"type": "tool_call", "tool": call["name"], "args": call["args"]})
        elif message.type == "tool":
            steps.append({"type": "tool_result", "tool": message.name, "content": message.content})
    return steps


def ask(question: str, thread_id: str | None = None) -> dict:
    """Run the router on one question. Pass a thread_id to continue a conversation."""
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph()
    before = len(graph.get_state(config).values.get("messages", []))

    final = graph.invoke({"messages": [HumanMessage(content=question)]}, config)
    new_messages = final["messages"][before:]
    answer = next(
        (m for m in reversed(new_messages) if isinstance(m, AIMessage) and not m.tool_calls),
        None,
    )
    return {
        "thread_id": thread_id,
        "answer": answer.text if answer else "(no answer: the step limit was reached)",
        "steps": _steps(new_messages),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the Olist router agent.")
    parser.add_argument("question", nargs="*", help="one question; omit for an interactive session")
    parser.add_argument("--thread", help="continue an existing thread_id")
    parser.add_argument("--trace", action="store_true", help="print each tool call and result")
    args = parser.parse_args()

    def run(question: str, thread_id: str | None) -> str:
        result = ask(question, thread_id)
        if args.trace:
            for step in result["steps"]:
                print(f"  [{step['type']}] {step['tool']}: {step.get('args', step.get('content'))}")
        print(result["answer"])
        return result["thread_id"]

    if args.question:
        print(f"thread: {run(' '.join(args.question), args.thread)}", file=sys.stderr)
        return 0

    thread_id = args.thread
    print("Ask a question (empty line to quit).")
    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            break
        if not question:
            break
        thread_id = run(question, thread_id)
    print(f"thread: {thread_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
