from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StepLog:
    tool: str
    status: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {"tool": self.tool, "status": self.status, "summary": self.summary}


@dataclass
class AnalysisResult:
    drop_percent: float
    insight: str
    top_country: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChartResult:
    mime_type: str
    base64_data: str

    def to_dict(self) -> dict[str, str]:
        return {"mime_type": self.mime_type, "base64_data": self.base64_data}


@dataclass
class AlertResult:
    triggered: bool
    delivered: bool
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SqlValidationResult:
    valid: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowResponse:
    heading: str
    sql: str | None
    validation: SqlValidationResult
    data_preview: list[dict[str, Any]]
    analysis: AnalysisResult
    chart: ChartResult
    alert: AlertResult
    formatted_response: str
    steps: list[StepLog]

    def to_dict(self) -> dict[str, Any]:
        return {
            "heading": self.heading,
            "sql": self.sql,
            "validation": self.validation.to_dict(),
            "data_preview": self.data_preview,
            "analysis": self.analysis.to_dict(),
            "chart": self.chart.to_dict(),
            "alert": self.alert.to_dict(),
            "formatted_response": self.formatted_response,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class ToolOutput:
    payload: dict[str, Any]
    summary: str


@dataclass
class ProductivityResult:
    actions: list[dict[str, Any]]
    snapshot: dict[str, list[dict[str, Any]]]
    summary: str
    steps: list[StepLog]

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": self.actions,
            "snapshot": self.snapshot,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class CopilotResponse:
    domains: list[str]
    summary: str
    analytics: dict[str, Any] | None
    productivity: dict[str, Any] | None
    steps: list[StepLog]

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": self.domains,
            "summary": self.summary,
            "analytics": self.analytics,
            "productivity": self.productivity,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class WorkflowContext:
    request_id: str
    question: str
    schema_context: str
    alert_threshold_percent: float
    step_logs: list[StepLog] = field(default_factory=list)

    def add_step(self, tool: str, status: str, summary: str) -> None:
        self.step_logs.append(StepLog(tool=tool, status=status, summary=summary))
