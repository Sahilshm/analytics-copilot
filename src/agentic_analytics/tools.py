from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

from .domain import AnalysisResult, ToolOutput, WorkflowContext
from .providers import ChartRenderer, LLMClient, Notifier, WarehouseClient


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    required_fields: tuple[str, ...]


class MCPTool(ABC):
    spec: ToolSpec

    def validate(self, payload: dict[str, Any]) -> None:
        missing = [field for field in self.spec.required_fields if field not in payload]
        if missing:
            raise ValueError(f"{self.spec.name} missing required fields: {', '.join(missing)}")

    @abstractmethod
    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        raise NotImplementedError


class GenerateSQLTool(MCPTool):
    spec = ToolSpec(
        name="generate_sql",
        description="Convert a natural-language question into SQL.",
        required_fields=("question",),
    )

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        sql = self.llm_client.generate_sql(str(payload["question"]), context.schema_context)
        return ToolOutput(payload={"sql": sql}, summary="Generated warehouse query from user intent.")


class ExecuteSQLTool(MCPTool):
    spec = ToolSpec(
        name="execute_sql",
        description="Execute SQL and return rows.",
        required_fields=("query",),
    )

    def __init__(self, warehouse_client: WarehouseClient) -> None:
        self.warehouse_client = warehouse_client

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        rows = self.warehouse_client.query(str(payload["query"]))
        return ToolOutput(payload={"rows": rows}, summary=f"Executed query and received {len(rows)} rows.")


class ValidateSQLTool(MCPTool):
    spec = ToolSpec(
        name="validate_sql",
        description="Validate SQL before execution.",
        required_fields=("sql",),
    )

    def __init__(self, warehouse_client: WarehouseClient) -> None:
        self.warehouse_client = warehouse_client

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        valid, reason = self.warehouse_client.validate_query(str(payload["sql"]))
        status = "validated" if valid else "rejected"
        return ToolOutput(
            payload={"validation": {"valid": valid, "reason": reason}},
            summary=f"SQL {status}: {reason}",
        )


class AnalyzeDataTool(MCPTool):
    spec = ToolSpec(
        name="analyze_data",
        description="Analyze query output for revenue changes and country contribution.",
        required_fields=("data",),
    )

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        rows = payload["data"]
        if not isinstance(rows, list):
            raise ValueError("analyze_data expects `data` to be a list of records.")
        analysis = analyze_rows(rows, str(payload.get("question", context.question)))
        summary = f"Computed {analysis.drop_percent:.1f}% drop"
        if analysis.top_country:
            summary += f"; top country driver is {analysis.top_country}."
        else:
            summary += "."
        return ToolOutput(payload={"analysis": analysis.to_dict()}, summary=summary)


class RenderChartTool(MCPTool):
    spec = ToolSpec(
        name="render_chart",
        description="Create a chart artifact for the query result.",
        required_fields=("data", "question"),
    )

    def __init__(self, chart_renderer: ChartRenderer) -> None:
        self.chart_renderer = chart_renderer

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        rows = payload["data"]
        if not isinstance(rows, list):
            raise ValueError("render_chart expects `data` to be a list of records.")
        chart = self.chart_renderer.render(rows, str(payload["question"]))
        return ToolOutput(payload={"chart": chart.to_dict()}, summary=f"Rendered chart as {chart.mime_type}.")


class SendAlertTool(MCPTool):
    spec = ToolSpec(
        name="send_alert",
        description="Send a notification for the workflow.",
        required_fields=("message",),
    )

    def __init__(self, notifier: Notifier) -> None:
        self.notifier = notifier

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        delivered = self.notifier.send(str(payload["message"]))
        return ToolOutput(payload={"delivered": delivered}, summary=f"Alert delivery result: {delivered}.")


class SendSlackMessageTool(MCPTool):
    spec = ToolSpec(
        name="send_slack_message",
        description="Send a communication message through the configured notifier backend.",
        required_fields=("message",),
    )

    def __init__(self, notifier: Notifier) -> None:
        self.notifier = notifier

    def invoke(self, payload: dict[str, Any], context: WorkflowContext) -> ToolOutput:
        self.validate(payload)
        delivered = self.notifier.send(str(payload["message"]))
        return ToolOutput(payload={"delivered": delivered}, summary=f"Slack/message delivery result: {delivered}.")


class ToolRegistry:
    def __init__(self, tools: list[MCPTool]) -> None:
        self._tools = {tool.spec.name: tool for tool in tools}

    def invoke(self, tool_name: str, payload: dict[str, Any], context: WorkflowContext) -> dict[str, Any]:
        if tool_name not in self._tools:
            raise KeyError(f"Unknown tool: {tool_name}")
        tool = self._tools[tool_name]
        try:
            result = tool.invoke(payload, context)
        except Exception as exc:
            context.add_step(tool_name, "failed", str(exc))
            raise
        context.add_step(tool_name, "completed", result.summary)
        return result.payload

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.spec.name,
                "description": tool.spec.description,
                "required_fields": list(tool.spec.required_fields),
            }
            for tool in self._tools.values()
        ]


def analyze_rows(rows: list[dict[str, Any]], question: str | None = None) -> AnalysisResult:
    if not rows:
        return AnalysisResult(drop_percent=0.0, insight="The query returned no rows to analyze.", top_country=None)

    normalized_question = (question or "").lower()
    keys = set(rows[0].keys())

    if "last month" in normalized_question and {"date", "revenue"}.issubset(keys):
        total = sum(float(row["revenue"]) for row in rows)
        best_day = max(rows, key=lambda row: float(row["revenue"]))
        insight = (
            f"Total sales for last month were {total:.2f}. "
            f"The strongest day was {best_day['date']} with revenue of {float(best_day['revenue']):.2f}."
        )
        return AnalysisResult(drop_percent=0.0, insight=insight)

    if "this year" in normalized_question and {"month", "revenue"}.issubset(keys):
        total = sum(float(row["revenue"]) for row in rows)
        best_month = max(rows, key=lambda row: float(row["revenue"]))
        insight = (
            f"Total sales for this year are {total:.2f}. "
            f"The strongest month so far is {best_month['month']} with revenue of {float(best_month['revenue']):.2f}."
        )
        return AnalysisResult(drop_percent=0.0, insight=insight)

    if any(token in normalized_question for token in ["by month, year", "by month year", "by month and year"]) and {
        "month",
        "revenue",
    }.issubset(keys):
        total = sum(float(row["revenue"]) for row in rows)
        best_month = max(rows, key=lambda row: float(row["revenue"]))
        insight = (
            f"Sales grouped by month-year total {total:.2f}. "
            f"The strongest month in the result set is {best_month['month']} with revenue of {float(best_month['revenue']):.2f}."
        )
        return AnalysisResult(drop_percent=0.0, insight=insight)

    if {"country", "previous_7_days_revenue", "last_7_days_revenue"}.issubset(keys):
        previous_total = sum(float(row["previous_7_days_revenue"]) for row in rows)
        last_total = sum(float(row["last_7_days_revenue"]) for row in rows)
        top_country = max(
            rows,
            key=lambda row: float(row["previous_7_days_revenue"]) - float(row["last_7_days_revenue"]),
        )["country"]
        drop_percent = calculate_drop_percent(previous_total, last_total)
        insight = (
            f"Revenue is down {drop_percent:.1f}% versus the previous 7 days. "
            f"{top_country} contributed the largest share of the decline."
        )
        return AnalysisResult(drop_percent=drop_percent, insight=insight, top_country=str(top_country))

    if {"country", "period", "revenue"}.issubset(keys):
        periods: dict[str, dict[str, float]] = {}
        for row in rows:
            country = str(row["country"])
            period = str(row["period"])
            periods.setdefault(country, {"previous_7_days": 0.0, "last_7_days": 0.0})
            periods[country][period] += float(row["revenue"])

        previous_total = sum(country_data["previous_7_days"] for country_data in periods.values())
        last_total = sum(country_data["last_7_days"] for country_data in periods.values())
        top_country = max(
            periods,
            key=lambda country: periods[country]["previous_7_days"] - periods[country]["last_7_days"],
        )
        drop_percent = calculate_drop_percent(previous_total, last_total)
        insight = (
            f"Revenue is down {drop_percent:.1f}% versus the prior 7-day window. "
            f"{top_country} shows the largest absolute drop."
        )
        return AnalysisResult(drop_percent=drop_percent, insight=insight, top_country=top_country)

    if {"date", "revenue"}.issubset(keys):
        ordered = sorted(rows, key=lambda row: row["date"])
        previous_rows = ordered[:-7][-7:]
        last_rows = ordered[-7:]
        previous_total = sum(float(row["revenue"]) for row in previous_rows)
        last_total = sum(float(row["revenue"]) for row in last_rows)
        drop_percent = calculate_drop_percent(previous_total, last_total)
        latest_date = last_rows[-1]["date"]
        insight = (
            f"Revenue across the latest 7 days ending {latest_date} is down {drop_percent:.1f}% "
            f"versus the previous 7 days."
        )
        return AnalysisResult(drop_percent=drop_percent, insight=insight)

    return AnalysisResult(drop_percent=0.0, insight="The returned rows do not match a supported analytics shape.")


def calculate_drop_percent(previous_total: float, last_total: float) -> float:
    if previous_total <= 0:
        return 0.0
    return round(max(0.0, ((previous_total - last_total) / previous_total) * 100), 2)
