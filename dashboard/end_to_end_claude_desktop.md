# End to end: ask questions about Olist data in Claude Desktop and build a dashboard

This walkthrough covers the whole use case: connect Claude Desktop to the Olist data, ask
questions in plain language, and turn the answers into a dashboard. It was run once, and
the report in this folder is the result.

## What you end up with

- A Claude Desktop chat that can read the Olist `marts` tables and search customer reviews.
- A monthly performance dashboard, saved as a single HTML file:
  [Olist Monthly Performance, Sep 2016 to Sep 2018.html](<Olist Monthly Performance, Sep 2016 to Sep 2018.html>).

## How it fits together

```
You, in Claude Desktop
   │  "How many orders per month?"
   ▼
Claude (writes the SQL, decides which tool to call)
   │  get_schema  ─────────►  marts schema card (from dbt's descriptions)
   │  run_sql     ─────────►  validate (one SELECT, marts only) ─► read-only role ─► Postgres
   │  search_reviews ──────►  embed question ─► pgvector search over review text
   ▼
Claude answers, or builds the dashboard as an artifact from the returned rows
```

The server does not call a model. Claude does the reasoning. The server checks each query
and runs it with a role that can only read the data. Setup details are in
[rag/mcp_server/README.md](../rag/mcp_server/README.md).

## 1. Connect the server

Follow [rag/mcp_server/README.md](../rag/mcp_server/README.md) once. In short:

1. Add the `olist` entry to Claude Desktop's config.
2. Quit Claude Desktop with Cmd+Q and reopen it.
3. In a new chat, ask: *"Call get_schema and list the tables."* Claude should list 10 tables.

The log for this server is at `~/Library/Logs/Claude/mcp-server-olist.log`.

## 2. Ask questions

Start with a few questions to see the tools work. These come from
[rag/mcp_server/example_questions.md](../rag/mcp_server/example_questions.md):

- *"Which 5 states have the most orders? Show the order count for each."*
  Expect SP first, with about 41.7k orders.
- *"What do customers complain about when a product arrives broken?"*
  Claude calls `search_reviews` and quotes Portuguese reviews, with its own English summary.
- *"How many late deliveries got a one-star review, and what did those customers say?"*
  Claude calls both tools and combines the count with quotes.

Check each answer three ways: the tool calls appear in the chat, the numbers match, and
Claude never attempts a write.

## 3. Build the dashboard

Paste the question-style prompt from [dashboard.md](dashboard.md) into a new chat. In short,
it asks Claude to:

- pull orders, revenue, average review score, and late-delivery percentage by month,
  excluding canceled and unavailable orders,
- show four summary cards, three charts, and a table,
- leave out the two low-volume months (Sep 2016 and Sep 2018) from the averages,
- format revenue as R$.

Claude runs its own SQL with `run_sql` and returns the dashboard as an artifact. Save the
artifact as an HTML file in this folder.

## 4. Check the numbers

The saved report has these values in its cards. They come from the monthly data in the
report, so you can check them against the database.

| Card | Value | How it is calculated |
|---|---|---|
| Total orders | 98,207 | sum of monthly orders, all months |
| Total revenue | R$ 15,739,137.01 | sum of monthly revenue, all months |
| Avg review score | 4.15 | mean of monthly averages, low-volume months left out |
| Avg late-delivery rate | 6.46% | mean of monthly rates, low-volume months left out |

To check the totals against the database, ask Claude: *"Total orders and total revenue, excluding
canceled and unavailable orders, across all months."* The totals should match the table above.

Two things to know about the averages:

- They are plain means of the monthly values. Each month counts equally, whatever its order
  count. A weighted average by orders would give a different number.
- The reference query in [dashboard.md](dashboard.md) returns one row per month that has orders.
  The report also has a November 2016 row with zero orders, because the data has no orders
  for that month. Claude added that row when it built the page.

## What happened behind the scenes

When you send a question, Claude runs a short loop:

1. It calls `get_schema` to learn the table and column names, and their descriptions.
2. It writes a SQL query based on that schema.
3. It calls `run_sql`. The server checks that the query is a single `SELECT` over `marts`,
   then runs it as the read-only role `olist_agent_ro`, with a 200-row cap and a 10-second
   timeout.
4. If the query fails, the error comes back to Claude, which can fix the SQL and try again.
5. For the dashboard, Claude uses the returned rows to write the HTML.

The descriptions Claude reads come from dbt. When a description changes in dbt's YAML, the
next `dbt build` updates what Claude sees. The server caches the schema for its lifetime,
so restart Claude Desktop after a dbt run.

## Limits

- **The dashboard is a snapshot.** The HTML contains the data as it was when Claude built
  it. It does not refresh when the database changes.
- **Claude writes the SQL each time.** A rerun may use a different query and get slightly
  different numbers, especially for questions with more than one reasonable definition.
  Make the definition explicit in the question, as the standalone SQL test does.
- **The charts load Chart.js from a CDN.** The report needs an internet connection to draw
  its charts. The numbers in the table do not.
- **Reviews are not de-duplicated by text.** The same review can appear once per order it
  covers. Two different reviews can also share the same text. Deduplicate on `review_id`
  when you need one row per review.
- **Server speed.** The first review search loads the embedding model, so it is slower than
  the rest.

## Troubleshooting

See the troubleshooting section in [rag/mcp_server/README.md](../rag/mcp_server/README.md).
If a number looks wrong, ask Claude to show the SQL it ran, then run that SQL with the
server's `run_sql` tool to compare.

## Next steps

This use case runs on a laptop, in one Claude Desktop chat at a time. The planned steps are:

- **Milestone 6:** a React front end and a FastAPI service with the router agent, so the
  dashboard can be live, shared, and used without Claude Desktop.
- **Milestone 7:** a remote MCP endpoint with authentication, so Claude.ai and ChatGPT can
  connect as well.
- **Deployment:** see [deployment.md](../deployment.md) for the cloud steps.
