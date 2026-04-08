from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import Settings
from .service import AppService, build_service


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural-language analytics question")


class CopilotRequest(BaseModel):
    prompt: str = Field(..., min_length=3, description="Natural-language multi-agent request")


class ChartResponse(BaseModel):
    mime_type: str
    base64_data: str


class AnalysisResponse(BaseModel):
    drop_percent: float
    insight: str
    top_country: str | None = None


class AlertResponse(BaseModel):
    triggered: bool
    delivered: bool
    message: str | None = None


class ValidationResponse(BaseModel):
    valid: bool
    reason: str


class StepResponse(BaseModel):
    tool: str
    status: str
    summary: str


class AskResponse(BaseModel):
    heading: str
    sql: str | None = None
    validation: ValidationResponse
    data_preview: list[dict[str, Any]]
    analysis: AnalysisResponse
    chart: ChartResponse
    alert: AlertResponse
    formatted_response: str
    steps: list[StepResponse]


class CopilotResponseModel(BaseModel):
    domains: list[str]
    summary: str
    analytics: dict[str, Any] | None = None
    productivity: dict[str, Any] | None = None
    steps: list[StepResponse]


def create_app(settings: Settings | None = None) -> FastAPI:
    service: AppService = build_service(settings)
    app = FastAPI(title="Agentic Analytics Copilot", version="0.1.0")
    app.state.service = service

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "name": "Agentic Analytics Copilot",
            "status": "ok",
            "message": "Use /health, /schema, /ask, or /copilot.",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health() -> dict[str, object]:
        return service.health()

    @app.get("/schema")
    async def schema() -> dict[str, object]:
        return service.schema()

    @app.get("/ask")
    async def ask_info() -> dict[str, object]:
        return {
            "message": "Use POST /ask with JSON: {\"question\": \"Show me sales for last month\"}",
            "docs": "/docs",
        }

    @app.post("/ask", response_model=AskResponse)
    async def ask(request: AskRequest) -> dict[str, object]:
        return service.ask(request.question)

    @app.get("/copilot")
    async def copilot_info() -> dict[str, object]:
        return {
            "message": "Use POST /copilot with JSON: {\"prompt\": \"Schedule a demo rehearsal tomorrow at 5pm\"}",
            "docs": "/docs",
        }

    @app.post("/copilot", response_model=CopilotResponseModel)
    async def copilot(request: CopilotRequest) -> dict[str, object]:
        return service.copilot(request.prompt)

    return app


app = create_app()
