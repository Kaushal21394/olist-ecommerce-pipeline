"""Tools the router agent can call. Each returns a JSON string the model reads.

The same two functions back the MCP server (Milestone 4b), so the safety
layers in sql_tool.py and review_search_tool.py apply to every front end.
"""

import json

from langchain_core.tools import tool

from review_search_tool import search_reviews as _search_reviews
from review_search_tool import summarize_hits
from sql_tool import answer_sql_question

MAX_ROWS_TO_MODEL = 50  # the model reads a sample; the full result is in the checkpoint
MAX_REVIEW_CHARS = 300


def _jsonable(value):
    return json.dumps(value, ensure_ascii=False, default=str)


@tool
def query_sql(question: str) -> str:
    """Answer a question that needs numbers from the Olist sales data.

    Use for counts, totals, averages, rankings, and filters over orders, sellers,
    products, customers, payments, and reviews as numbers. Pass the question in
    plain language, with the time period and filters spelled out. Returns the SQL
    that was run, the column names, and the rows (up to 50 shown).

    Use this for a count/total/ranking even on a follow-up about reviews search_reviews
    already returned (e.g. "out of those, how many were 1-star?") — search_reviews only
    returns a small sample, so tallying it instead of calling this tool gives a wrong
    number.
    """
    result = answer_sql_question(question)
    rows = [list(row) for row in result["rows"] or []]
    return _jsonable({
        "sql": result["sql"],
        "error": result["error"],
        "columns": result["columns"],
        "rows": rows[:MAX_ROWS_TO_MODEL],
        "row_count": len(rows),
        "truncated": result["truncated"],
    })


@tool
def search_reviews(
    query: str,
    limit: int = 5,
    min_score: int | None = None,
    max_score: int | None = None,
    state: str | None = None,
    late: bool | None = None,
) -> str:
    """Find customer review texts about a topic, by meaning.

    Use when the answer depends on what customers said or why, such as complaints,
    praise, or a specific problem. The query can be in Portuguese or English. Filters
    narrow the reviews first: min_score and max_score are 1-5, state is a 2-letter
    Brazilian state code (e.g. "SP"), and late is true for late deliveries and false
    for on-time ones. Returns the closest reviews, best match first, with score and
    state.
    """
    try:
        hits = _search_reviews(
            query, limit=limit, min_score=min_score, max_score=max_score, state=state, late=late,
        )
    except ValueError as exc:  # a bad filter value; tell the model rather than crash the run
        return _jsonable({"error": str(exc), "reviews": []})
    return _jsonable(summarize_hits(hits, max_chars=MAX_REVIEW_CHARS))


TOOLS = [query_sql, search_reviews]
