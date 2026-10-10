# Pulse: Project Guide for Claude Code

## What Pulse is
Pulse is a plug-and-play analytics tool for developers. A developer installs it, runs one command (`pulse start`), and instantly gets a local analytics dashboard for their app. No Docker, no cloud accounts, no config files needed.

It started as a "DuckDB/Parquet Analytics & Experiment Toolkit" course project brief. We are now building it as a one-command developer tool instead of a multi-part toolkit. The original goals (event SDKs, Parquet storage, DuckDB queries, dashboards, A/B testing) all still apply.

## About the developer (read this first)
- I am building this **solo**, on **Windows** (project folder: `Documents\PROJECTS\pulse`). Use Windows-friendly commands (PowerShell / cmd), not Linux-only ones.
- I want to **understand** what is happening. Explain things in plain, simple words. Avoid jargon, or explain it in one line when you must use it.
- Add short comments in the code explaining what each part does and why.
- Work **one phase at a time**. Do not jump ahead to later phases.
- My goal is to **finish** this project. Get the MVP (Phases 0 to 6) fully working before touching any stretch goal.

## How to work with me
1. At the start of each session, look at the current state of the repo and tell me which phase we are on and what is already done.
2. Before writing code for a phase, give me a short plan (3 to 6 bullets) and wait for my OK.
3. After writing code, **run it and test it yourself**. Do not say "done" until you have seen it work. If something fails, fix it.
4. When a phase works, tell me in simple words what was built and how I can try it myself.
5. Then commit to git with a clear message like `phase 1: event ingestion works`. Make sure `.gitignore` covers `.pulse/`, `__pycache__/`, `node_modules/`, `.venv/`, and any build output that should not be committed.
6. Tick the finished phase in the **Progress** section at the bottom of this file.

## Core design rule
Everything runs in **ONE process**, started by `pulse start`. No separate ingest server, no separate dashboard server. One command boots everything.

```
Your app (with Pulse SDK)
        |  sends batched events over HTTP
        v
+---------------------------------------+
|  Local server (pulse start)           |
|   - Ingest API: receives events       |
|   - Query engine (DuckDB): reads data |
|   - Experiment engine: A/B tests      |
|   - Serves the dashboard files        |
+---------------------------------------+
        |                     |
        v                     v
 Parquet files on disk   Dashboard in browser
   (.pulse/events/)        (localhost:4747)
```

## Tech stack
- **Backend:** Python 3.10+, FastAPI, uvicorn
- **Storage:** Parquet files on disk (the files ARE the database), written with pyarrow (or polars)
- **Querying:** DuckDB, reading the Parquet folder directly
- **Dashboard:** React, built once and served as static files by the same server. No separate dev server when a user runs Pulse. (Superset/Metabase from the original brief are dropped because they need their own setup.)
- **TypeScript SDK:** for frontends. Buffers events and sends them in batches.
- **Python SDK:** for backends. Same idea, same event format.
- **CI:** GitHub Actions (run tests on push)

## Out of scope (do NOT build)
Paid warehouses (BigQuery/Snowflake), Kafka or other streaming ingestion, advanced ML pipelines, real-time ML prediction serving, paid data lake, multi-tenant user billing, and anything that requires Docker or a cloud account to run.

## Event format (the contract everything depends on)
Every event has these fields:

| Field | Meaning |
|---|---|
| `timestamp` | when it happened (UTC, ISO format) |
| `actor` | who did it (user id, anonymous id, or service name) |
| `entity` | what it was done to (page, button, order, etc.) |
| `action` | what happened (click, view, purchase, etc.) |
| `metadata` | extra details as a JSON object |

Keep this format stable. If it must change, tell me why first.

## Planned folder layout
```
pulse/
  CLAUDE.md
  pyproject.toml
  README.md
  pulse/                  <- Python package
    __init__.py
    cli.py                <- the `pulse` command
    server.py             <- FastAPI app
    schema.py             <- event format + validation
    ingest.py             <- receives events, writes Parquet
    storage.py            <- where/how Parquet files are laid out
    query.py              <- DuckDB queries (counts, funnels, retention)
    experiments.py        <- A/B test assignment + analysis
    static/               <- built dashboard files
  dashboard/              <- React source code
  sdk-js/                 <- TypeScript SDK
  sdk-python/             <- Python SDK (or pulse/sdk/)
  examples/sample-app/    <- tiny demo app that sends events
  tests/
```
This is a guide, not a strict rule. If a simpler layout works better, suggest it.

## Phases

### Phase 0: Skeleton
`pulse start` boots a FastAPI server and opens the browser to a placeholder page. Has `--port` (default 4747) and `--no-browser` flags, plus a `/health` endpoint.
**Done when:** `pip install -e .` works, `pulse start` runs, and the browser shows the placeholder.

### Phase 1: Event pipeline
- Define the event format in `schema.py` and validate incoming events.
- `POST /ingest` accepts a batch (list) of events as JSON.
- Events are buffered in memory and written to Parquet files in `.pulse/events/`, split into folders by date (e.g. `date=2026-10-10/`).
- Bad events are rejected with a clear error message, without crashing the whole batch.

**Done when:** I can send events with a test script and see Parquet files appear on disk.

### Phase 2: Query layer
- DuckDB reads the Parquet folder directly.
- REST endpoints for: event counts over time, top actions/entities, funnels, retention.
- Simple "saved queries" so the dashboard just calls an endpoint.

**Done when:** endpoints return correct numbers for test data, and aggregation over 1M events takes **under 1 second**.

### Phase 3: Dashboard
- React app with 3 core views: **Overview** (counts + trends), **Funnels**, **Retention**.
- Built once, output goes into `pulse/static/`, served by the same server.
- Clean look, works with no setup, and shows a friendly empty state when there is no data yet.

**Done when:** `pulse start` shows real charts from real events.

### Phase 4: SDKs
- **TypeScript SDK:** `pulse.track(action, entity, metadata)`. Batches events, retries on failure, tiny size, and never crashes the host app.
- **Python SDK:** same behavior and same event format.
- A sample app in `examples/` that uses the SDK so I can demo everything.

**Done when:** the sample app's events show up on the dashboard, with SDK overhead **under 2%** on the sample app.

### Phase 5: Experiment engine (A/B testing)
- Assignment: hash the user id + experiment name so each user always gets the same variant.
- Collect the chosen metric for each variant from the events.
- Analysis: difference in means + bootstrap confidence interval, with a plain-English summary.
- A dashboard tab to view results.

**Done when:** an experiment report generates in **under 5 seconds** with a stats summary.

### Phase 6: Packaging and polish
- A great README (install, run, add the SDK in 3 steps).
- A PyPI-ready package (dashboard build included).
- `pulse init` for optional config, `pulse reset` to clear data.
- A demo-data command so the dashboard looks good on first run.
- GitHub Actions running the tests.

### Stretch (only after everything above works)
Thompson Sampling (bandit) helper, feature store (key-value online + offline Parquet), browser notebook with DuckDB-WASM, data quality checks (schema drift, null-ratio alerts).

## Success targets
1. Dashboard aggregation query: **< 1 s** for up to 1M local events
2. SDK overhead: **< 2%** performance impact on the sample app
3. Experiment report: **< 5 s** including the statistical summary

## Code rules
- Keep it simple. Pick the boring, easy-to-read solution over the clever one.
- Small files, small functions, clear names.
- Write a few tests for each phase (pytest for Python) and run them before committing.
- Never write data outside the `.pulse/` folder (or a folder the user configures).
- The server listens on `127.0.0.1` only (this machine), never on all network interfaces.
- Don't add new libraries without telling me what they do and why we need them.
- If something in this file seems wrong or outdated, tell me and suggest an update instead of silently working around it.

## Progress
- [ ] Phase 0: Skeleton
- [ ] Phase 1: Event pipeline
- [ ] Phase 2: Query layer
- [ ] Phase 3: Dashboard
- [ ] Phase 4: SDKs
- [ ] Phase 5: Experiment engine
- [ ] Phase 6: Packaging and polish
- [ ] Stretch goals
