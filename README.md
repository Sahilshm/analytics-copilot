# Agentic Analytics Copilot

Agentic Analytics Copilot is a cloud-first, multi-agent system that combines **analytics querying** with **productivity workflows**. It turns natural-language analytics questions into SQL, executes them on BigQuery, analyzes results, generates charts, and handles task/calendar/note management—all through a unified agent interface.

The project includes:
- **FastAPI backend** for API-first analytics (`POST /ask`, `POST /copilot`)
- **ADK web UI** for an interactive agent-powered chat experience
- **Multi-agent coordination**: planner agent routes requests, execution agent calls tools sequentially
- **Flexible backends**: Vertex AI or rule-based LLMs, BigQuery or demo data, Slack or log notifications, SQLite or Postgres for tasks/notes

## Key Features

- 🤖 **Multi-agent orchestration**: Planner routes requests, Executor calls analytics & productivity tools
- 📊 **Natural-language analytics**: SQL generation → execution → analysis → visualization
- 📋 **Productivity integration**: Create tasks, schedule events, save notes directly from analytics insights
- 🔄 **Slack formatting**: Automatically converts markdown tables and code blocks to Slack-friendly format
- 💾 **Full data preservation**: Notes capture complete analytics responses with all markdown
- 🌐 **Web UI + REST API**: Choose interactive chat (ADK) or programmatic access (FastAPI)
- ☁️ **Cloud-ready**: Deployed on Cloud Run with Vertex AI, BigQuery, Cloud SQL, Secret Manager

## Architecture

```
User Input
    ↓
PlannerAgent (routing)
    ↓
ExecutionAgent (tool orchestration)
    ├─ analytics_question()
    │  └─ PrimaryCoordinatorAgent
    │     ├─ SqlAgent (generate SQL)
    │     ├─ ExecuteSQLTool (run query)
    │     ├─ AnalyzeDataTool (compute insights)
    │     └─ RenderChartTool (create visualization)
    ├─ save_note(title, content) → create_note in registry
    ├─ send_slack_message(message) → markdown→Slack formatter
    ├─ create_task, retrieve_notes, etc.
    └─ Response (text + optional chart artifact)
```

### Core Components

| Component | Purpose |
|-----------|---------|
| **PlannerAgent** | Routes requests; outputs one-liner routing plan (no reasoning bloat) |
| **ExecutionAgent** | Executes tools in sequence; preserves full markdown in responses |
| **PrimaryCoordinatorAgent** | Orchestrates SQL → execution → analysis → chart pipeline |
| **ProductivityAgent** | Handles task/calendar/note CRUD operations |
| **CopilotCoordinatorAgent** | Hybrid router: analytics + productivity domains |
| **ToolRegistry** | MCP-style tool validation and invoke with structured logging |
| **_markdown_to_slack()** | Converts markdown tables/headings to Slack mrkdwn format |
| **_normalize_columns()** | Maps SQL aliases (e.g., `order_date` → `date`) for analysis |

## Quick Start

### Local Mock Mode (No GCP Required)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run FastAPI server
uvicorn agentic_analytics.main:app --reload
# Visit http://localhost:8000/docs

# Or run ADK web UI
pip install -e ".[adk]"
adk web ./adk_agents
# Visit http://localhost:8080
```

**Try it:**
```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Top 5 products by revenue for Q1 2026"}'
```

### With GCP (BigQuery + Vertex AI)

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-gcp-project
export LLM_BACKEND=vertex
export WAREHOUSE_BACKEND=bigquery
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

pip install -e ".[cloud,adk]"
adk web ./adk_agents
```

## Configuration

| Variable | Default | Options |
|----------|---------|---------|
| `LLM_BACKEND` | `rule_based` | `vertex`, `rule_based` |
| `WAREHOUSE_BACKEND` | `demo` | `bigquery`, `demo` |
| `NOTIFIER_BACKEND` | `log` | `slack`, `log` |
| `PRODUCTIVITY_STORE_BACKEND` | `sqlite` | `sqlite`, `postgres` |
| `VERTEX_MODEL` | `gemini-2.5-flash` | Any Vertex model |
| `ALERT_THRESHOLD_PERCENT` | `20` | % revenue drop to trigger alert |

See `.env.demo` and `.env.paused` for preset configs.

## Agent Behavior

### Planner Agent
- **Input**: User query
- **Output**: Single routing sentence (e.g., `"Call analytics_question to get top products, then send_slack_message with result"`)
- **Design**: No reasoning bloat, no greeting responses—pure routing

### Execution Agent
- **Input**: User query + routing plan
- **Output**: Executes tools in sequence; returns complete analytics response with markdown
- **Key behavior**:
  - Preserves **full** markdown (tables, SQL blocks, analysis)
  - When saving notes: uses complete `formatted_response` (not truncated)
  - For Slack: passes full response through markdown→Slack converter

### Data Flow Example

**User**: `"Show me daily revenue trend for the last 30 days, then send it to Slack"`

1. **Planner**: `"Call analytics_question, then send_slack_message with the result"`
2. **Executor**:
   - Calls `analytics_question("Show me daily revenue trend for the last 30 days")`
   - Gets back: `# Daily revenue trend...  ## Analysis ... ## Data | date | revenue | ...`
   - Calls `send_slack_message(full_response)`
   - Slack notifier applies `_markdown_to_slack()` converter:
     - `# Title` → `*Title*` (bold)
     - `| table |` → ` ```\n| table |\n``` ` (monospace)
     - ````sql` → kept as-is
   - Returns: `"✓ Daily revenue trend delivered to Slack"`

## Database & Persistence

### Local SQLite (default)
```bash
export SQLITE_DB_PATH=./copilot.db
```
Auto-creates tasks, calendar events, notes in a local SQLite DB.

### Cloud SQL Postgres
```bash
export PRODUCTIVITY_STORE_BACKEND=postgres
export POSTGRES_DSN=postgresql://user:password@/copilot?host=/cloudsql/instance
```
Used in production Cloud Run deployments.

## Deployment

### Cloud Run (FastAPI)
```bash
gcloud run deploy agentic-analytics-copilot \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars LLM_BACKEND=vertex,WAREHOUSE_BACKEND=bigquery
```

### Cloud Run (ADK Web + FastAPI)
```bash
# Build ADK image
gcloud builds submit . --config cloudbuild.adk.yaml

# Deploy
gcloud run deploy agentic-copilot-adk \
  --image us-central1-docker.pkg.dev/PROJECT/repo/agentic-copilot-adk:latest \
  --region us-central1 \
  --allow-unauthenticated
```

## Testing

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Covers:
- SQL generation for analytics queries
- Revenue drop analysis + country drivers
- Tool registry validation
- Hybrid workflows (analytics + productivity)
- End-to-end integration

## Troubleshooting
## Scripts

All scripts are in `./scripts/`:

| Script | Purpose |
|--------|---------|
| `prepare_retail_data.py` | Clean Kaggle Online Retail CSV and split into 3 tables |
| `load_bigquery.py` | Load prepared data into BigQuery |
| `deploy_cloudrun_postgres.sh` | Deploy to Cloud Run with Cloud SQL + Secret Manager |
| `migrate_productivity_sqlite_to_postgres.py` | Migrate local SQLite data to production Postgres |
| `pause_project.sh` | Switch to low-cost demo mode (rule-based LLM, demo data) |
| `resume_demo.sh` | Restore BigQuery demo setup |
| `gcloudw.sh` | Wrapper for gcloud to use local config when needed |


### Notes not capturing full content
- Check execution agent instruction: must include `"CRITICAL: When passing analytics data to save_note, use the COMPLETE formatted response..."`
- Ensure `save_note()` calls registry directly (not via `SERVICE.copilot()`)

### Slack messages truncated
- Verify `_markdown_to_slack()` converter is active in `providers.py`
- Check webhook URL is valid and the bot has permissions

### Charts not showing
- Charts are attached as ADK artifacts (not embedded base64)
- ADK web UI renders artifacts inline; REST API includes base64 in response
- For REST API debugging: check `response["chart"]["base64_data"]` is present

## Contributing

- Use `dev` branch for development
- Run tests before submitting PRs
- Update docstrings for public functions
- Follow existing code style (black, mypy compatible)

For more details, see the repository documentation.

## License

MIT

