"""Milestone 2 standalone check: run the SQL agent against known questions.

Each case has a hand-written reference query. The reference runs through the
same read-only role as the agent, and its rows are the expected answer. A case
passes when the agent's rows match the reference rows, in order (the references
use ORDER BY). Column names are ignored; values are compared.

Numbers match within max(0.05, 1e-6 * size), so rounding differences pass but
an off-by-one count does not. Error cases pass when the agent returns an error
and no rows.

    python rag/agent/standalone_test.py            # summary
    python rag/agent/standalone_test.py -v         # also show SQL and mismatches
"""

import math
import sys

import sql_tool

CASES = [
    {
        "name": "total orders",
        "question": "How many orders are in the dataset in total?",
        "reference": "SELECT count(*) FROM marts.fct_orders",
    },
    {
        "name": "delivered revenue",
        "question": "What is the total revenue from delivered orders, in BRL, rounded to whole reais?",
        "reference": "SELECT round(sum(total_payment_value)) FROM marts.fct_orders WHERE order_status = 'delivered'",
    },
    {
        "name": "top categories by items",
        # "not counting canceled or unavailable" pins the definition. Without it, both
        # readings are valid and the answer depends on which one the model picks.
        "question": "Which 5 product categories sold the most items, not counting canceled or unavailable orders? Give the category and the item count.",
        "reference": """
            SELECT p.product_category_name, count(*) AS items
            FROM marts.fct_order_items i
            JOIN marts.dim_products p USING (product_id)
            WHERE i.order_status NOT IN ('canceled', 'unavailable')
            GROUP BY p.product_category_name
            ORDER BY items DESC, p.product_category_name
            LIMIT 5
        """,
    },
    {
        "name": "review score late vs on time",
        "question": "Across every review left (not just the latest review per order), what is the average review score for delivered orders that were late versus on time? Show the two averages.",
        "reference": """
            SELECT is_late_delivery, round(avg(review_score), 2)
            FROM marts.mart_review_base
            WHERE order_status = 'delivered' AND is_late_delivery IS NOT NULL
            GROUP BY is_late_delivery
            ORDER BY is_late_delivery
        """,
    },
    {
        "name": "RFM segment sizes",
        "question": "How many customers are in each RFM segment? Sort by count, highest first.",
        "reference": """
            SELECT rfm_segment, count(*)
            FROM marts.mart_customer_rfm
            GROUP BY rfm_segment
            ORDER BY count(*) DESC, rfm_segment
        """,
    },
    {
        "name": "top sellers by revenue",
        "question": "Which 3 sellers have the highest total revenue? Include each seller's state.",
        "reference": """
            SELECT seller_id, seller_state, round(total_revenue, 2)
            FROM marts.mart_seller_performance
            ORDER BY total_revenue DESC, seller_id
            LIMIT 3
        """,
    },
    {
        "name": "orders by state in 2018",
        "question": "Which 3 customer states placed the most orders in 2018?",
        "reference": """
            SELECT customer_state, count(*)
            FROM marts.fct_orders
            WHERE order_purchase_timestamp >= '2018-01-01' AND order_purchase_timestamp < '2019-01-01'
            GROUP BY customer_state
            ORDER BY count(*) DESC, customer_state
            LIMIT 3
        """,
    },
    {
        "name": "unanswerable from marts",
        "question": "What was the weather in Sao Paulo on 1 May 2018?",
        "expect_error": True,
    },
    {
        "name": "write attempt refused",
        "question": "Delete all canceled orders from the orders table.",
        "expect_error": True,
    },
]


def values_match(got, want) -> bool:
    if got is None or want is None:
        return got is want
    if isinstance(got, str) or isinstance(want, str):
        return str(got) == str(want)
    a, b = float(got), float(want)
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=0.05)


def rows_match(got_rows, want_rows) -> bool:
    if len(got_rows) != len(want_rows):
        return False
    for got, want in zip(got_rows, want_rows):
        if len(got) != len(want) or not all(values_match(g, w) for g, w in zip(got, want)):
            return False
    return True


def run_case(case: dict) -> tuple[bool, str, dict]:
    result = sql_tool.answer_sql_question(case["question"])

    if case.get("expect_error"):
        ok = result["error"] is not None and not result["rows"]
        return ok, "error as expected" if ok else "expected an error, got rows", result

    if result["error"]:
        return False, f"agent error: {result['error']}", result

    _, want_rows, _ = sql_tool.run_sql(case["reference"])
    ok = rows_match(result["rows"], want_rows)
    detail = f"{len(result['rows'])} rows, reference {len(want_rows)}"
    if not ok:
        detail += f"\n      expected: {want_rows}\n      got:      {result['rows']}"
    return ok, detail, result


def main(verbose: bool) -> int:
    failures = 0
    for case in CASES:
        ok, detail, result = run_case(case)
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case['name']}: {detail}")
        if verbose and result.get("sql"):
            print("      SQL:", " ".join(result["sql"].split()))
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(verbose="-v" in sys.argv))
