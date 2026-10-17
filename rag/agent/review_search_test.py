"""Milestone 3 standalone check: run the review search against qualitative questions.

Two kinds of check:
  - Hard rules. Filters must hold on every row, results must be at most `limit`,
    and similarity must be sorted best first. A failure here is a bug.
  - Relevance, as a proxy. Relevance is judged by keyword: at least `min_hits`
    of the top results must contain one of the Portuguese keywords for the topic.
    This is a rough signal, not a quality score. Read the -v output to judge the
    actual results.

    python rag/agent/review_search_test.py          # summary
    python rag/agent/review_search_test.py -v       # also show the top results
"""

import sys

import review_search_tool as rs

CASES = [
    {
        "name": "broken product",
        "query": "produto chegou quebrado",
        "filters": {},
        "keywords": ["quebr", "danific", "defeit", "estrag", "avaria"],
        "min_hits": 3,
    },
    {
        "name": "never arrived",
        "query": "nunca recebi o pedido",
        "filters": {},
        "keywords": ["não recebi", "nao recebi", "não chegou", "nao chegou", "nunca chegou",
                     "não veio", "nao veio", "não foi entregue", "nao foi entregue"],
        "min_hits": 2,
    },
    {
        "name": "late delivery filter",
        "query": "entrega atrasada",
        "filters": {"late": True},
        "keywords": ["atras", "demor", "prazo"],
        "min_hits": 2,
    },
    {
        "name": "wrong item, low score",
        "query": "produto diferente do anunciado",
        "filters": {"max_score": 2},
        "keywords": ["errad", "diferente", "anunciad", "outro", "não é o que", "nao é o que"],
        "min_hits": 2,
    },
    {
        "name": "state filter",
        "query": "atendimento ruim da loja",
        "filters": {"state": "SP"},
        "keywords": ["atendimento", "suporte", "resposta", "vendedor", "loja", "contato"],
        "min_hits": 2,
    },
    {
        "name": "restrictive filter still fills limit",
        "query": "produto chegou quebrado",
        "filters": {"max_score": 1, "state": "AC"},
        "keywords": [],  # hard rules only
        "min_hits": 0,
        "limit": 5,
        "expect_full": True,
    },
    {
        # Without the iterative scan, HNSW returned 1 row for this filter.
        "name": "late filter still fills limit",
        "query": "produto chegou quebrado",
        "filters": {"late": True},
        "keywords": [],
        "min_hits": 0,
        "limit": 5,
        "expect_full": True,
    },
]


def check_filters(hit: dict, filters: dict) -> bool:
    if "late" in filters and hit["is_late_delivery"] is not filters["late"]:
        return False
    if "max_score" in filters and not hit["review_score"] <= filters["max_score"]:
        return False
    if "min_score" in filters and not hit["review_score"] >= filters["min_score"]:
        return False
    if "state" in filters and hit["customer_state"] != filters["state"]:
        return False
    return True


def run_case(case: dict) -> tuple[bool, str, list[dict]]:
    limit = case.get("limit", 5)
    hits = rs.search_reviews(case["query"], limit=limit, **case["filters"])

    problems = []
    if len(hits) > limit:
        problems.append(f"returned {len(hits)} rows, limit is {limit}")
    if case.get("expect_full") and len(hits) != limit:
        problems.append(f"returned {len(hits)} rows, expected {limit} (iterative scan may be off)")
    bad_filter = [h for h in hits if not check_filters(h, case["filters"])]
    if bad_filter:
        problems.append(f"{len(bad_filter)} row(s) break the filter")
    sims = [h["similarity"] for h in hits]
    if sims != sorted(sims, reverse=True):
        problems.append("results are not sorted best first")

    top = hits[:5]
    text_hits = [h for h in top if any(k in (h["review_text"] or "").lower() for k in case["keywords"])]
    if case["keywords"] and len(text_hits) < case["min_hits"]:
        problems.append(f"only {len(text_hits)} of top {len(top)} match topic keywords (need {case['min_hits']})")

    detail = f"{len(hits)} rows"
    if case["keywords"]:
        detail += f", {len(text_hits)}/{len(top)} topic hits"
    if problems:
        detail += " | " + "; ".join(problems)
    return not problems, detail, hits


def check_validation() -> bool:
    try:
        rs.search_reviews("teste", min_score=7)
    except ValueError:
        return True
    return False


def main(verbose: bool) -> int:
    failures = 0
    for case in CASES:
        ok, detail, hits = run_case(case)
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case['name']}: {detail}")
        if verbose:
            for h in hits[:5]:
                text = " ".join((h["review_text"] or "").split())
                print(f"      {h['similarity']:.3f}  score={h['review_score']}  {h['customer_state']}  {text[:110]}")

    valid_ok = check_validation()
    failures += not valid_ok
    print(f"[{'PASS' if valid_ok else 'FAIL'}] invalid filter rejected: min_score=7 raises ValueError")

    total = len(CASES) + 1
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(verbose="-v" in sys.argv))
