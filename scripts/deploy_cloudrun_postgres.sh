#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GCLOUDW="$ROOT_DIR/scripts/gcloudw.sh"

PROJECT_ID="${PROJECT_ID:-${GCP_PROJECT_ID:-}}"
REGION="${REGION:-us-central1}"

API_SERVICE="${API_SERVICE:-agentic-analytics-copilot}"
ADK_SERVICE="${ADK_SERVICE:-agentic-copilot-adk}"

BIGQUERY_DATASET="${BIGQUERY_DATASET:-analytics_copilot}"
BIGQUERY_LOCATION="${BIGQUERY_LOCATION:-US}"
VERTEX_LOCATION="${VERTEX_LOCATION:-us-central1}"
VERTEX_MODEL="${VERTEX_MODEL:-gemini-2.5-flash}"

INSTANCE_CONNECTION_NAME="${INSTANCE_CONNECTION_NAME:-}"
POSTGRES_DSN_SECRET="${POSTGRES_DSN_SECRET:-copilot-postgres-dsn}"
SLACK_WEBHOOK_SECRET="${SLACK_WEBHOOK_SECRET:-copilot-slack-webhook}"
POSTGRES_DSN_VALUE="${POSTGRES_DSN_VALUE:-}"
SLACK_WEBHOOK_URL_VALUE="${SLACK_WEBHOOK_URL_VALUE:-}"

ADK_IMAGE="${ADK_IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${ADK_SERVICE}:latest}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "Set PROJECT_ID (or GCP_PROJECT_ID) before running this script."
  exit 1
fi

if [[ -z "$INSTANCE_CONNECTION_NAME" ]]; then
  echo "Set INSTANCE_CONNECTION_NAME to your Cloud SQL instance connection name."
  echo "Example: project-id:us-central1:agentic-copilot-pg"
  exit 1
fi

if [[ -z "$POSTGRES_DSN_VALUE" ]]; then
  echo "Set POSTGRES_DSN_VALUE to your Postgres DSN before running this script."
  exit 1
fi

if [[ -z "$SLACK_WEBHOOK_URL_VALUE" ]]; then
  echo "Set SLACK_WEBHOOK_URL_VALUE to your Slack webhook URL before running this script."
  exit 1
fi

ensure_secret() {
  local secret_name="$1"
  if ! "$GCLOUDW" secrets describe "$secret_name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    "$GCLOUDW" secrets create "$secret_name" --replication-policy="automatic" --project "$PROJECT_ID"
  fi
}

add_secret_version() {
  local secret_name="$1"
  local secret_value="$2"
  printf "%s" "$secret_value" | "$GCLOUDW" secrets versions add "$secret_name" --data-file=- --project "$PROJECT_ID"
}

"$GCLOUDW" services enable run.googleapis.com sqladmin.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com --project "$PROJECT_ID"

ensure_secret "$POSTGRES_DSN_SECRET"
ensure_secret "$SLACK_WEBHOOK_SECRET"
add_secret_version "$POSTGRES_DSN_SECRET" "$POSTGRES_DSN_VALUE"
add_secret_version "$SLACK_WEBHOOK_SECRET" "$SLACK_WEBHOOK_URL_VALUE"

COMMON_ENV="APP_ENV=production,LLM_BACKEND=vertex,WAREHOUSE_BACKEND=bigquery,NOTIFIER_BACKEND=slack,PRODUCTIVITY_STORE_BACKEND=postgres,GCP_PROJECT_ID=${PROJECT_ID},BIGQUERY_DATASET=${BIGQUERY_DATASET},BIGQUERY_LOCATION=${BIGQUERY_LOCATION},VERTEX_LOCATION=${VERTEX_LOCATION},VERTEX_MODEL=${VERTEX_MODEL},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${VERTEX_LOCATION},GOOGLE_GENAI_USE_VERTEXAI=true"
COMMON_SECRETS="POSTGRES_DSN=${POSTGRES_DSN_SECRET}:latest,SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_SECRET}:latest"

"$GCLOUDW" run deploy "$API_SERVICE" \
  --source "$ROOT_DIR" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars "$COMMON_ENV" \
  --set-secrets "$COMMON_SECRETS" \
  --add-cloudsql-instances "$INSTANCE_CONNECTION_NAME"

"$GCLOUDW" builds submit "$ROOT_DIR" --config "$ROOT_DIR/cloudbuild.adk.yaml" --substitutions="_IMAGE=${ADK_IMAGE}" --project "$PROJECT_ID"

"$GCLOUDW" run deploy "$ADK_SERVICE" \
  --image "$ADK_IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars "$COMMON_ENV" \
  --set-secrets "$COMMON_SECRETS" \
  --add-cloudsql-instances "$INSTANCE_CONNECTION_NAME"

echo "Deployment complete."
echo "- API service: $API_SERVICE"
echo "- ADK service: $ADK_SERVICE"
echo "- Productivity backend: Postgres via secret $POSTGRES_DSN_SECRET"
echo "- Slack backend: webhook via secret $SLACK_WEBHOOK_SECRET"
