# Deployment

How to move the Olist project from a laptop to a cloud environment. The steps are
provider-neutral: they name what each piece needs, not a specific vendor. Pick a provider
in step 0, then fill in the provider-specific commands.

Current state: everything runs locally. Postgres is on `localhost:5432` (`olist_db`), dbt
builds the marts there, and the MCP server runs over stdio for Claude Desktop only. The
React front end (Milestone 6) and the remote MCP transport (Milestone 7) are not built
yet, so their steps are marked **future**.

## What gets deployed

| Component | Today | Cloud target |
|---|---|---|
| PostgreSQL 16+ with `pgvector` | local | managed Postgres with the `vector` extension |
| Schemas and roles (`sql/001`–`009`) | local | same migrations, applied in order |
| dbt project (`dbt/olist`) | local | run as a job against the cloud database |
| Bronze data loader (`ingestion/batch`) | local, from `data/raw` | run once per data refresh |
| Review embeddings | a local, unpublished notebook | a script, run as a job (see step 6) |
| MCP server (`rag/mcp_server`) | stdio, Claude Desktop | **future:** HTTP transport with auth (Milestone 7) |
| Router agent (`rag/agent/router.py`) | CLI | **future:** behind the API (Milestone 6) |
| Front end (`frontend/`) | not built | **future:** Milestone 6 |

## 0. Decide the provider (one-time)

Choose:

- **Database:** a managed Postgres service that supports the `pgvector` extension. Check the
  provider's extension list before you commit. The steps below assume `pgvector` is available.
- **App host:** a container platform, for the API and the MCP server (once they are built).
- **Secrets:** the provider's secret store, or a managed vault. Never commit credentials.

Record the choices in this file under "Provider choices" so the rest of the steps match.

## 1. Pre-deploy: clean up the repo

- [ ] **`~/.dbt/profiles.yml` holds the database password in plain text.** Use an
      `env_var()` reference in the profile, so the password comes from the environment.
- [ ] **`.env` must not be committed.** Confirm it is in `.gitignore`.

## 2. Create the cloud database

1. Create a managed Postgres instance with a major version of 16 or later.
2. Enable the extension once, as the admin role:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

   `sql/001` also creates extensions. Check that it runs without error on the new instance.
3. Restrict network access to the app host and to your workstation. Do not open it to the
   public internet.
4. Turn on automated backups and point-in-time recovery.

## 3. Create roles and set their passwords

The migrations create three roles. Set each password separately, from a secret store, never
in a SQL file.

| Role | Used by | Access |
|---|---|---|
| admin (owner) | migrations, dbt, bronze loader | owns the schemas |
| `olist_agent_ro` | MCP server, router SQL tool, review search | read-only on `marts` and `vector.review_embeddings` |
| `olist_agent_state` | LangGraph checkpoints | write access to `agent_state` only |

```bash
# Run as the admin role. Read each password from the secret store, not from the terminal history.
psql "$ADMIN_DATABASE_URL" -c "ALTER ROLE olist_agent_ro PASSWORD '$(secret-get agent-ro-password)'"
psql "$ADMIN_DATABASE_URL" -c "ALTER ROLE olist_agent_state PASSWORD '$(secret-get agent-state-password)'"
```

Replace `secret-get` with your provider's CLI command.

## 4. Apply the migrations in order

Apply the files in name order. Each one is written to be re-runnable (`IF NOT EXISTS`), so
a retry is safe.

```bash
for f in sql/00*.sql; do
  echo "applying $f"
  psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done
```

`003` and `004` create the streaming and CDC tables from the parked Phases 3 and 4. They are
harmless if unused, so apply them to keep the schema the same as local.

## 5. Load the data and build the marts

1. Load the bronze tables from `data/raw` with the batch loader. Use a variable for the
   connection, not a fallback password:

   ```bash
   export PGHOST=<cloud host> PGDATABASE=olist_db PGUSER=<admin user> PGPASSWORD=$(secret-get admin-password)
   ./.venv/bin/python ingestion/batch/load_bronze.py
   ```

   The bronze COPY path has only been tested against a temp table. Run it on a copy of the
   database first, and check the row counts against local.

2. Build the dbt project, which also writes the table and column descriptions the agent
   reads (`persist_docs`):

   ```bash
   cd dbt/olist
   DBT_PASSWORD=$(secret-get admin-password) dbt build --target cloud
   ```

   Add a `cloud` target to `profiles.yml` that reads host, user, and password from
   environment variables.

3. Check the descriptions landed. The schema card the agent reads comes from them:

   ```sql
   SELECT obj_description('marts.fct_orders'::regclass, 'pg_class');
   ```

   The result should be the model description from dbt's YAML, not empty.

## 6. Build the review embeddings

Embedding runs once per data load. Today it is a notebook. Before it runs in the cloud, move
it into a script, so it can be scheduled and rerun without Jupyter:

- Read `marts.mart_review_base` in batches, embed with
  `paraphrase-multilingual-mpnet-base-v2`, and insert into `vector.review_embeddings` with
  `executemany`. The primary key is `(review_id, order_id)` (`sql/009`), so a rerun must
  either skip existing keys or truncate the table first.
- The model is about 1 GB on disk. Bake it into the container image, or mount a cache
  volume, so the job doesn't download it on every run.
- Embedding 40,968 reviews is a batch job, not a request-time task.

**Future:** add the script to the repo as `rag/embeddings/embed_reviews.py`.

## 7. Package and deploy the app

The app is a Python project with `requirements.txt` at the root. For a container:

1. Write a `Dockerfile` (not in the repo yet) that installs `requirements.txt`, copies `rag/`,
   and runs the server.
2. Pass configuration as environment variables. Do not put secrets in the image.

   | Variable | Who needs it |
   |---|---|
   | `AGENT_DATABASE_URL` | MCP server, router, review search (role `olist_agent_ro`) |
   | `AGENT_CHECKPOINT_DATABASE_URL` | router, SQL graph (role `olist_agent_state`) |
   | `ANTHROPIC_API_KEY` | router, SQL generation only. The MCP server does not need it. |

3. **MCP server, today:** it speaks stdio, so it runs only on the machine that starts it.
   Claude Desktop is the only client, and the cloud database is reached over the network
   from that machine. Set `AGENT_DATABASE_URL` in `.env` for the cloud host.
4. **Future (Milestone 7):** add the HTTP transport to `rag/mcp_server/server.py`
   (`mcp.run(transport="streamable-http")`), put it behind TLS, and add authentication before
   exposing it. Claude.ai and ChatGPT both need a public HTTPS endpoint.
5. **Future (Milestone 6):** deploy the FastAPI service and the React build. The API reads
   the router's checkpoints, so it needs `AGENT_CHECKPOINT_DATABASE_URL`.

## 8. Smoke tests after each deploy

Run these against the cloud database, from the app host or a machine with the same `.env`:

```bash
./.venv/bin/python rag/agent/standalone_test.py       # expect 9/9
./.venv/bin/python rag/agent/review_search_test.py    # expect 8/8
./.venv/bin/python rag/mcp_server/mcp_test.py          # expect 9/9
```

The SQL and review tests call the Claude API and the embedding model, so they cost a little
each run. The MCP test does not call Claude.

Confirm the safety layers on the cloud role too, not just locally:

```bash
psql "$AGENT_DATABASE_URL" -c "DELETE FROM marts.fct_orders"      # must fail: permission denied
psql "$AGENT_DATABASE_URL" -c "SELECT count(*) FROM bronze.orders" # must fail: no access
```

## 9. Operations

- **Schedule:** the bronze load and the dbt build, when new data arrives. Re-embed reviews
  after each dbt build that changes `mart_review_base`.
- **Schema card cache:** the agent caches the schema card per process. Restart the app
  after a dbt run changes descriptions.
- **Backups:** confirm that point-in-time recovery works with a restore to a new instance.
- **Logs:** the MCP server writes to stderr. Ship it to the provider's log service.
- **Costs:** each router or SQL question calls the Claude API. Set a monthly spend limit on
  the API key.

## 10. Rollback

- **Migrations:** the SQL files have no down migrations. Restore from a backup taken before
  the change, or write a reversing migration as a new numbered file.
- **dbt:** redeploy the previous git commit and run `dbt build` against it.
- **App:** redeploy the previous container image.

## Decisions still open

- Which provider, and whether it has managed `pgvector`.
- Whether the MCP server runs on a cloud host (needs Milestone 7) or stays local.
- How data refreshes are scheduled, and whether the raw data is loaded from files or from
  a source system.
- Whether the React front end is hosted with the API or on a static host.
