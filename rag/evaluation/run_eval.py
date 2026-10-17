"""Milestone 5 eval harness: score the router (and the tool layer it shares with
the MCP server) against a golden set of questions.

Two passes per case:
  - Tool layer: `reference_sql` runs through sql_guard (the same validate_sql ->
    run_sql path the MCP server's run_sql tool uses) and `review_search` runs
    through review_search_tool.search_reviews (the same path the MCP server's
    search_reviews tool uses). No model call, so this fails fast if the schema
    or the search break, independent of anything the router decides.
  - Router: the question goes through the full router (model picks tools,
    answers in prose). The check is necessarily fuzzy -- the answer is free
    text -- so it looks for the expected values/keywords inside it, and for
    the expected tool names in the run's trace.

This is a baseline, not a certainty: a correct answer that rephrases a number
can still fail the substring check, and a wrong one can accidentally contain
the right digits. Read -v output to judge borderline cases by eye. Run this
once before changing a prompt and once after, and compare the two reports.

    python rag/evaluation/run_eval.py                 # summary
    python rag/evaluation/run_eval.py -v               # also show answers and traces
    python rag/evaluation/run_eval.py --filter seller  # only cases whose id matches
    python rag/evaluation/run_eval.py --router-only    # skip the tool-layer pass
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import review_search_tool  # noqa: E402
import router as router_mod  # noqa: E402
import sql_guard  # noqa: E402

GOLDEN_SET = Path(__file__).resolve().parent / "golden_set.json"

# Matches a run of digits with comma and/or dot separators, e.g. "1,234", "4.29",
# "7.827" (Brazilian thousands-dot) or "1.234,56" (Brazilian decimal-comma).
NUMBER_RE = re.compile(r"-?\d[\d,.]*\d|-?\d")

DEFAULT_REFUSAL_WORDS = [
    "cannot", "can't", "unable", "no data", "not available", "don't have",
    "doesn't have", "not in the", "no information", "won't", "will not", "refus",
    "não posso", "não tenho", "não é possível",
]
PT_HINT_RE = re.compile(
    r"[ãõáéíóúçÃÕÁÉÍÓÚÇ]|\b(pedidos?|foram|atrasados?|entregas?|total|clientes?)\b",
    re.IGNORECASE,
)


def load_cases(filter_text: str | None = None) -> list[dict]:
    cases = json.loads(GOLDEN_SET.read_text())
    if filter_text:
        cases = [c for c in cases if filter_text in c["id"]]
    return cases


def _number_candidates(token: str) -> list[float]:
    """Every plausible numeric reading of one matched token.

    US/UK style ("15,422,462"), a plain decimal ("4.29"), and mixed style
    ("1.234,56") each have one reading. A lone dot followed by exactly three
    digits ("7.827") is genuinely ambiguous -- Brazilian thousands-dot or a
    literal decimal -- so both readings are returned and either one counts
    as a match.
    """
    has_comma, has_dot = "," in token, "." in token
    try:
        if has_comma and has_dot:
            decimal_sep = token[max(token.rfind(","), token.rfind("."))]
            thousands_sep = "." if decimal_sep == "," else ","
            return [float(token.replace(thousands_sep, "").replace(decimal_sep, "."))]
        if has_comma:
            return [float(token.replace(",", ""))]
        if has_dot:
            frac = token.rpartition(".")[2]
            if token.count(".") == 1 and len(frac) == 3:
                return [float(token.replace(".", "")), float(token)]
            if token.count(".") > 1:  # "15.422.462": every dot is a thousands separator
                return [float(token.replace(".", ""))]
        return [float(token)]
    except ValueError:
        return []


def extract_numbers(text: str) -> list[float]:
    numbers = []
    for match in NUMBER_RE.findall(text):
        numbers.extend(_number_candidates(match))
    return numbers


def value_in_answer(value, answer: str, numbers: list[float]) -> bool:
    if isinstance(value, bool):
        return str(value).lower() in answer.lower()
    if isinstance(value, str):
        return value.lower() in answer.lower()
    try:
        as_float = float(value)  # covers int, float, and psycopg's Decimal
    except (TypeError, ValueError):
        return str(value).lower() in answer.lower()
    return any(math.isclose(as_float, n, rel_tol=1e-6, abs_tol=0.5) for n in numbers)


def expected_values(case: dict) -> list:
    """Flatten the leading rows of `reference_sql`, dropping NULLs (nothing to find)."""
    clean = sql_guard.validate_sql(case["reference_sql"])
    _, rows, _ = sql_guard.run_sql(clean)
    n = case.get("value_rows", 1)
    values = []
    for row in rows[:n]:
        values.extend(v for v in row if v is not None)
    return values


def check_tool_layer(case: dict) -> tuple[bool, str]:
    problems = []
    if case.get("reference_sql"):
        try:
            clean = sql_guard.validate_sql(case["reference_sql"])
            sql_guard.run_sql(clean)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the run
            problems.append(f"reference_sql failed: {exc}")
    if case.get("review_search"):
        spec = case["review_search"]
        try:
            review_search_tool.search_reviews(spec["query"], **spec.get("filters", {}))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"review_search failed: {exc}")
    return not problems, "; ".join(problems)


def check_router(case: dict, thread_ids: dict[str, str]) -> tuple[bool, str, dict]:
    thread_id = thread_ids.get(case["follow_up_of"]) if case.get("follow_up_of") else None
    result = router_mod.ask(case["question"], thread_id)
    thread_ids[case["id"]] = result["thread_id"]
    answer = result["answer"]
    numbers = extract_numbers(answer)
    problems = []

    tools_called = {step["tool"] for step in result["steps"] if step["type"] == "tool_call"}
    missing_tools = [t for t in case.get("expect_tools", []) if t not in tools_called]
    if missing_tools:
        problems.append(f"tool(s) {missing_tools} not called (called {sorted(tools_called)})")

    if case.get("reference_sql"):
        values = expected_values(case)
        hits = [v for v in values if value_in_answer(v, answer, numbers)]
        min_hits = case.get("min_value_hits", len(values))
        if len(hits) < min_hits:
            problems.append(f"{len(hits)}/{len(values)} expected values found (need {min_hits}): {values}")

    if case.get("keywords"):
        text_hits = [k for k in case["keywords"] if k.lower() in answer.lower()]
        min_hits = case.get("min_keyword_hits", 1)
        if len(text_hits) < min_hits:
            problems.append(f"{len(text_hits)}/{len(case['keywords'])} keywords found (need {min_hits})")

    if case.get("expect_refusal"):
        refusal_words = case.get("refusal_keywords", DEFAULT_REFUSAL_WORDS)
        if not any(w in answer.lower() for w in refusal_words):
            problems.append("no refusal language detected")

    if case.get("language_hint") == "pt" and not PT_HINT_RE.search(answer):
        problems.append("answer does not look like Portuguese")

    return not problems, "; ".join(problems) if problems else "ok", result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Milestone 5 eval harness against golden_set.json.")
    parser.add_argument("-v", "--verbose", action="store_true", help="show the answer and trace per case")
    parser.add_argument("--router-only", action="store_true", help="skip the tool-layer pass")
    parser.add_argument("--filter", help="only run cases whose id contains this substring")
    args = parser.parse_args()

    cases = load_cases(args.filter)
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 1

    thread_ids: dict[str, str] = {}
    tool_fail = router_fail = 0

    for case in cases:
        if not args.router_only:
            ok, detail = check_tool_layer(case)
            tool_fail += not ok
            print(f"[{'PASS' if ok else 'FAIL'}] {case['id']} (tool layer)" + (f": {detail}" if detail else ""))

        ok, detail, result = check_router(case, thread_ids)
        router_fail += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case['id']} (router): {detail}")
        if args.verbose:
            print(f"      answer: {result['answer']}")
            for step in result["steps"]:
                print(f"      [{step['type']}] {step['tool']}: {step.get('args', step.get('content'))}")

    total = len(cases)
    if not args.router_only:
        print(f"\ntool layer: {total - tool_fail}/{total} passed")
    print(f"router: {total - router_fail}/{total} passed")
    return 1 if (tool_fail or router_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
