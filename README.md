# Agentic Analytics Copilot

Agentic Analytics Copilot is a cloud-first FastAPI service that combines an analytics copilot with task, calendar, and notes workflows. It turns natural-language analytics questions into SQL, executes them on data, analyzes the result, generates a chart, and can also create tasks, schedule events, and save notes through MCP-style tools. The core demo path targets Cloud Run + Vertex AI + BigQuery + Slack, while a local mock mode keeps the project testable without cloud credentials.

## What it does

- Accepts analytics questions through `POST /ask`
- Accepts hybrid productivity + analytics workflows through `POST /copilot`
- Coordinates a primary analytics agent plus sub-agents and productivity workflows
- Calls MCP-style tools for SQL generation, query execution, analysis, charting, alerts, tasks, calendar events, and notes
- Returns SQL, result preview, chart data, insight text, alert status, and productivity actions
- Exposes `GET /health` and `GET /schema` for operational visibility

## Architecture

- `PrimaryCoordinatorAgent`: owns the workflow and final response assembly
- `SqlAgent`: generates warehouse-aware SQL for the retail schema
- `InsightAgent`: computes drop percentage and leading country driver
- `ProductivityAgent`: creates or retrieves tasks, calendar events, and notes
- `CopilotCoordinatorAgent`: routes requests across analytics and productivity domains
- `ToolRegistry`: validates and invokes MCP-style tools with structured logs
- `ProductivityStore`: pluggable storage for tasks, schedules, and notes (`sqlite` or `postgres`)
- Providers:
  - `VertexLLMClient` or `RuleBasedLLMClient`
  - `BigQueryWarehouseClient` or `DemoWarehouseClient`
  - `SlackNotifier` or `LogNotifier`
  - `MatplotlibChartRenderer` or `SvgChartRenderer`

## Quick start

1. Create a virtual environment and install the package:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Run locally in mock mode:

   ```bash
   uvicorn agentic_analytics.main:app --reload
   ```

3. Call the API:

   ```bash
   curl -X POST http://127.0.0.1:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question":"Which country contributed most to revenue drop?"}'
   ```

   ```bash
   curl -X POST http://127.0.0.1:8000/copilot \
     -H "Content-Type: application/json" \
     -d '{"prompt":"Schedule a demo rehearsal tomorrow at 5pm, create a task to finalize slides, and save a note that the BigQuery demo tables are ready."}'
   ```

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Runtime environment label |
| `LLM_BACKEND` | `rule_based` | `vertex` or `rule_based` |
| `WAREHOUSE_BACKEND` | `demo` | `bigquery` or `demo` |
| `NOTIFIER_BACKEND` | `log` | `slack` or `log` |
| `ALERT_THRESHOLD_PERCENT` | `20` | Trigger threshold for alerts |
| `GOOGLE_APPLICATION_CREDENTIALS` | unset | Path to a service-account JSON for ADC auth |
| `GOOGLE_CLOUD_PROJECT` | unset | Project ID for ADK/Google GenAI Vertex routing |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Region for ADK/Google GenAI Vertex routing |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` | Forces ADK and Google GenAI to use Vertex AI instead of API-key mode |
| `GCP_PROJECT_ID` | unset | GCP project for BigQuery and Vertex |
| `BIGQUERY_DATASET` | `analytics_copilot` | BigQuery dataset name |
| `BIGQUERY_LOCATION` | `US` | BigQuery and Vertex region |
| `VERTEX_LOCATION` | `us-central1` | Vertex AI region |
| `VERTEX_MODEL` | `gemini-2.5-flash` | Vertex model name |
| `TRANSACTIONS_TABLE` | `transactions` | Transactions table name inside the dataset |
| `CUSTOMERS_TABLE` | `customers` | Customers table name inside the dataset |
| `PRODUCTS_TABLE` | `products` | Products table name inside the dataset |
| `PRODUCTIVITY_STORE_BACKEND` | `sqlite` | `sqlite` or `postgres` |
| `SQLITE_DB_PATH` | `./copilot.db` | SQLite database used for tasks, calendar events, and notes |
| `POSTGRES_DSN` | unset | Postgres DSN used when `PRODUCTIVITY_STORE_BACKEND=postgres` |
| `SLACK_WEBHOOK_URL` | unset | Slack Incoming Webhook |
| `DEMO_ANCHOR_DATE` | today | Anchor date for local demo data |

## GCP connection

For local development against real GCP services, install the cloud extras and authenticate with either `gcloud auth application-default login` or a service account JSON:

```bash
source .venv/bin/activate
pip install -e ".[cloud]"
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=your-gcp-project
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=true
export GCP_PROJECT_ID=your-gcp-project
export BIGQUERY_DATASET=analytics_copilot
export BIGQUERY_LOCATION=US
export VERTEX_LOCATION=us-central1
export LLM_BACKEND=vertex
export WAREHOUSE_BACKEND=bigquery
export NOTIFIER_BACKEND=slack
export PRODUCTIVITY_STORE_BACKEND=postgres
export POSTGRES_DSN=postgresql://user:password@host:5432/database
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

If you prefer `gcloud`, set the project and application-default credentials after installing the Cloud SDK:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project your-gcp-project
```

The bundled wrapper script `./scripts/gcloudw.sh` will use your normal `~/.config/gcloud` setup when it exists, and only fall back to a project-local config if needed.

## Data preparation

Use `scripts/prepare_retail_data.py` to clean the Kaggle Online Retail CSV and split it into the three target tables:

```bash
python scripts/prepare_retail_data.py \
  --input /path/to/OnlineRetail.csv \
  --output-dir ./prepared_data
```

Then load the output into BigQuery:

```bash
python scripts/load_bigquery.py \
  --project your-gcp-project \
  --dataset analytics_copilot \
  --location US \
  --transactions ./prepared_data/transactions.csv \
  --customers ./prepared_data/customers.csv \
  --products ./prepared_data/products.csv
```

The prep step injects the demo signal by reducing revenue for the latest 7-day window by 40%.

## Cloud Run deployment

For hosted submission-grade persistence, use Cloud SQL Postgres for productivity data and Secret Manager for DSN/webhook values.

```bash
PROJECT_ID=your-gcp-project
INSTANCE_CONNECTION_NAME=your-gcp-project:us-central1:agentic-copilot-pg
POSTGRES_DSN_VALUE='postgresql://copilot_app:password@/copilot?host=/cloudsql/your-gcp-project:us-central1:agentic-copilot-pg'
SLACK_WEBHOOK_URL_VALUE='https://hooks.slack.com/services/...'

PROJECT_ID="$PROJECT_ID" \
INSTANCE_CONNECTION_NAME="$INSTANCE_CONNECTION_NAME" \
POSTGRES_DSN_VALUE="$POSTGRES_DSN_VALUE" \
SLACK_WEBHOOK_URL_VALUE="$SLACK_WEBHOOK_URL_VALUE" \
./scripts/deploy_cloudrun_postgres.sh
```

Install cloud dependencies during deployment with:

```bash
pip install -e ".[cloud]"
```

## Migrate Existing SQLite Productivity Data

After provisioning Cloud SQL, migrate any existing local productivity records:

```bash
python scripts/migrate_productivity_sqlite_to_postgres.py \
  --sqlite-path ./copilot.db \
  --postgres-dsn "$POSTGRES_DSN_VALUE"
```

Use `--dry-run` to preview row counts and `--truncate-target` for a replace-style migration.

## ADK and Cloud Run

This repo now supports two deployment shapes:

- `FastAPI` app at `agentic_analytics.main:app`
- `ADK` app at `adk_main:app`

For the ADK path, install:

```bash
pip install -e ".[cloud,adk]"
```

The ADK agent files are:

- `adk_agents/hybrid_copilot/agent.py`
- `adk_main.py`
- `Dockerfile.adk`

To run the ADK FastAPI server locally after installing the ADK extra:

```bash
uvicorn adk_main:app --reload
```

To run the ADK web UI locally with Vertex AI instead of API-key mode:

```bash
adk web ./adk_agents
```

This relies on:

- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION`
- `GOOGLE_GENAI_USE_VERTEXAI=true`
- your existing ADC login from `gcloud auth application-default login`

## Test coverage

The tests exercise:

- SQL generation for the supported demo queries
- Revenue drop analysis and country attribution logic
- Alert threshold behavior
- Tool schema validation
- Hybrid analytics + productivity orchestration
- End-to-end workflow orchestration with local mock providers

Run tests with:

```bash
python -m unittest discover -s tests
```

## Pause and Resume

To avoid cloud usage until demo day, switch the project into low-cost paused mode:

```bash
./scripts/pause_project.sh
```

That sets:

- `LLM_BACKEND=rule_based`
- `WAREHOUSE_BACKEND=demo`
- `NOTIFIER_BACKEND=log`

To restore the prepared BigQuery demo setup:

```bash
./scripts/resume_demo.sh
```

That restores:

- `WAREHOUSE_BACKEND=bigquery`
- `TRANSACTIONS_TABLE=transactions_demo`
- `CUSTOMERS_TABLE=customers_demo`
- `PRODUCTS_TABLE=products_demo`

The current live demo config is also stored in `.env.demo`, and the paused config is stored in `.env.paused`.
