"""Semantic search over review text: embed the question, find the nearest reviews, filter.

The question is embedded with the same model the reviews were embedded with
(EMBEDDING_MODEL below), so both live in the same vector space.
Vectors are normalized, so cosine similarity is a dot product and pgvector's
<=> operator (cosine distance) ranks correctly.

Filters (score range, state, late delivery) are applied in the same SQL query
as the vector search, as bound parameters. Filter values never go into the SQL
text.

    python rag/agent/review_search_tool.py "produto chegou quebrado" --max-score 2
"""

import argparse
import functools
import os

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv()

EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"  # must match the ingested embeddings
EMBEDDING_DIM = 768
MAX_LIMIT = 20
HNSW_EF_SEARCH = 100  # candidates HNSW considers before filtering; higher = better recall, slower


@functools.cache
def embedder() -> SentenceTransformer:
    """Load the embedding model once per process (it takes a few seconds)."""
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_query(text: str):
    vector = embedder().encode(text, normalize_embeddings=True)
    assert vector.shape == (EMBEDDING_DIM,), f"expected {EMBEDDING_DIM} dims, got {vector.shape}"
    return vector


def _connect():
    """Read-only connection as the agent role (sql/006, plus the grant in sql/008)."""
    conn = psycopg.connect(os.environ["AGENT_DATABASE_URL"])
    conn.read_only = True
    # The role's search_path is marts (sql/006), but the pgvector type and its
    # operators (<=>, ::vector) live in public. Add public so they resolve. The
    # role has no grants on anything in public, so this exposes nothing.
    conn.execute("SET search_path = marts, public")
    register_vector(conn)  # lets psycopg send numpy arrays as the vector type
    conn.commit()  # keep the search_path change for the session
    return conn


def _check_filters(min_score, max_score, state, late) -> None:
    for name, value in (("min_score", min_score), ("max_score", max_score)):
        if value is not None and not (1 <= value <= 5):
            raise ValueError(f"{name} must be between 1 and 5, got {value}")
    if state is not None and len(state) != 2:
        raise ValueError(f"state must be a 2-letter code, got {state!r}")


def build_search_query(
    *,
    min_score: int | None = None,
    max_score: int | None = None,
    state: str | None = None,
    late: bool | None = None,
) -> tuple[str, list]:
    """Return (WHERE clause, filter parameters) for the given filters.

    The clause text is built only from fixed fragments. Each value is a %s
    placeholder, so no filter value ever becomes part of the SQL text.
    """
    _check_filters(min_score, max_score, state, late)
    clauses, params = [], []
    if min_score is not None:
        clauses.append("review_score >= %s")
        params.append(min_score)
    if max_score is not None:
        clauses.append("review_score <= %s")
        params.append(max_score)
    if state is not None:
        clauses.append("customer_state = %s")
        params.append(state.upper())
    if late is not None:
        clauses.append("is_late_delivery = %s")
        params.append(late)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


SEARCH_SQL = """
    SELECT review_id, order_id, review_text, review_score,
           customer_state, is_late_delivery,
           1 - (embedding <=> %s) AS similarity
    FROM vector.review_embeddings
    {where}
    ORDER BY embedding <=> %s
    LIMIT %s
"""


def search_reviews(
    query: str,
    *,
    limit: int = 5,
    min_score: int | None = None,
    max_score: int | None = None,
    state: str | None = None,
    late: bool | None = None,
) -> list[dict]:
    """Return the reviews closest in meaning to `query`, best match first.

    Filters narrow the candidates before ranking. Each row carries a similarity
    score between -1 and 1 (higher is closer).
    """
    limit = max(1, min(limit, MAX_LIMIT))
    where, filter_params = build_search_query(
        min_score=min_score, max_score=max_score, state=state, late=late,
    )
    sql = SEARCH_SQL.format(where=where)  # `where` holds only fixed fragments
    vector = embed_query(query)
    # The vector appears twice: once for the similarity column, once for the ordering.
    params = [vector, *filter_params, vector, limit]

    conn = _connect()
    try:
        with conn.cursor() as cur:
            # SET LOCAL lasts for this transaction only.
            cur.execute(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}")
            # With a filter, the index can run out of candidates and return fewer
            # rows than LIMIT. Iterative scan keeps reading the index until it has enough.
            cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            cur.execute(sql, params)
            columns = [col.name for col in cur.description]
            rows = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()

    return [dict(zip(columns, row)) for row in rows]


def summarize_hits(hits: list[dict], max_chars: int = 300) -> list[dict]:
    """Shape search rows for a model: rounded similarity, the fields that matter, trimmed text."""
    return [
        {
            "similarity": round(hit["similarity"], 3),
            "review_score": hit["review_score"],
            "customer_state": hit["customer_state"],
            "is_late_delivery": hit["is_late_delivery"],
            "review_text": " ".join((hit["review_text"] or "").split())[:max_chars],
        }
        for hit in hits
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search review text by meaning.")
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--min-score", type=int)
    parser.add_argument("--max-score", type=int)
    parser.add_argument("--state")
    late = parser.add_mutually_exclusive_group()
    late.add_argument("--late", dest="late", action="store_true")
    late.add_argument("--on-time", dest="late", action="store_false")
    parser.set_defaults(late=None)
    args = parser.parse_args()

    hits = search_reviews(
        args.query, limit=args.limit, min_score=args.min_score, max_score=args.max_score,
        state=args.state, late=args.late,
    )
    for hit in hits:
        text = " ".join((hit["review_text"] or "").split())
        print(f"{hit['similarity']:.3f}  score={hit['review_score']}  {hit['customer_state']}  "
              f"late={hit['is_late_delivery']}  {text[:140]}")
    if not hits:
        print("no reviews matched")
