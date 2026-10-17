# Olist MCP server: setup for Claude Desktop

The server lets Claude Desktop query the Olist `marts` schema and search customer review
text. Claude writes the SQL. The server checks it, runs it read-only, and returns rows.

Tools:

| Tool | What it does |
|---|---|
| `get_schema` | Returns the marts schema card, built from dbt's table and column descriptions |
| `run_sql` | Runs one validated read-only `SELECT` over `marts.*` (200-row cap, 10 s timeout) |
| `search_reviews` | Finds review text by meaning, with score, state, and late-delivery filters |

## 1. Prerequisites

- The project virtualenv with the requirements installed:
  `./.venv/bin/pip install -r requirements.txt`
- `.env` in the repo root with `AGENT_DATABASE_URL` set (the read-only role from `sql/006`).
  The server reads it by absolute path, so Claude Desktop needs no secrets.
- The embedding model cached locally (`paraphrase-multilingual-mpnet-base-v2`). It is
  downloaded on first use.
- Claude Desktop installed (`/Applications/Claude.app`).

## 2. Check the server runs

From the repo root:

```bash
./.venv/bin/python rag/mcp_server/mcp_test.py
```

Expect `9/9 passed`. This starts the server as a subprocess and calls every tool over the
MCP protocol, so it covers the same path Claude Desktop uses.

## 3. Add the server to Claude Desktop

Open the Claude Desktop config:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Add the `olist` entry inside the existing `mcpServers` object. If the object is missing,
create it. Do not add a second `mcpServers` key.

```json
"mcpServers": {
  "olist": {
    "command": "/Users/<you>/Projects/olist/.venv/bin/python",
    "args": ["/Users/<you>/Projects/olist/rag/mcp_server/server.py"]
  }
}
```

Replace `<you>` with your user name. The file in this folder,
[claude_desktop_config.json](claude_desktop_config.json), shows the same entry on its own.

Keep a backup of the config before you edit it.

## 4. Restart Claude Desktop

Quit with **Cmd+Q**. Closing the window is not enough, because the server only loads on
launch. Reopen the app.

## 5. Confirm it is connected

In a new chat, the olist tools appear in the tools menu. You can also ask:

> "Call get_schema and list the tables."

Claude should list 10 `marts` tables. If the tools are missing, see the troubleshooting
section below.

## Troubleshooting

- **Tools don't appear.** Check that the JSON is valid (`python3 -m json.tool <config file>`),
  that the paths in `command` and `args` exist, and that you quit with Cmd+Q.
- **A tool returns a database error.** Check that `.env` has `AGENT_DATABASE_URL`, and that
  the role can connect: run `./.venv/bin/python rag/mcp_server/mcp_test.py`.
- **The first review search is slow.** It loads the embedding model. Later calls are fast.
- **A dbt change isn't visible.** The schema card is cached per server process. Restart
  Claude Desktop after a dbt run.
- **Server logs.** Claude Desktop writes this server's log to
  `~/Library/Logs/Claude/mcp-server-olist.log`. Check it first when a tool fails.

## Security notes

- The server connects as the read-only role `olist_agent_ro`. It can only read `marts` and
  `vector.review_embeddings`.
- `run_sql` accepts one `SELECT` and rejects writes, other schemas, multiple statements,
  and functions such as `pg_sleep`. The database role also blocks writes, so the check is
  not the only layer.
- The server listens on stdio only. Nothing is exposed on the network.

## Related files

- [server.py](server.py): the MCP server
- [mcp_test.py](mcp_test.py): protocol test
- [../agent/sql_guard.py](../agent/sql_guard.py): validation and read-only execution
- [example_questions.md](example_questions.md): questions to try in Claude
- [dashboard.md](dashboard.md): the monthly dashboard prompt
