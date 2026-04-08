from __future__ import annotations

import os

from fastapi import FastAPI

try:
    from google.adk.cli.fast_api import get_fast_api_app
except ImportError as exc:  # pragma: no cover - optional dependency
    raise RuntimeError("Install ADK support with `pip install -e \".[adk]\"`.") from exc


AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adk_agents")
SERVE_WEB_INTERFACE = os.getenv("ADK_WEB_UI", "true").lower() == "true"

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_db_kwargs={"db_url": "sqlite+aiosqlite:///./adk_sessions.db"},
    allow_origins=["*"],
    use_local_storage=True,
    web=SERVE_WEB_INTERFACE,
)

app.title = "Agentic Copilot ADK Service"
app.description = "ADK-compatible Cloud Run deployment for the hybrid analytics and productivity copilot."
