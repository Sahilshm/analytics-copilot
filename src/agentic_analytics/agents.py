from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .config import Settings
from .domain import (
    AlertResult,
    AnalysisResult,
    ChartResult,
    CopilotResponse,
    ProductivityResult,
    SqlValidationResult,
    StepLog,
    WorkflowContext,
    WorkflowResponse,
)
from .productivity_tools import (
    extract_event_query,
    extract_event_title,
    extract_note_content,
    extract_note_query,
    extract_slack_message,
    extract_task_title,
    parse_datetime_text,
    productivity_intent,
)
from .schema import build_schema_context
from .tools import ToolRegistry


@dataclass
class AgentResult:
    payload: dict[str, Any]


class SqlAgent:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def run(self, question: str, context: WorkflowContext) -> AgentResult:
        payload = self.registry.invoke("generate_sql", {"question": question}, context)
        return AgentResult(payload=payload)


class InsightAgent:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def run(self, question: str, rows: list[dict[str, Any]], context: WorkflowContext) -> AgentResult:
        payload = self.registry.invoke("analyze_data", {"data": rows, "question": question}, context)
        analysis = payload["analysis"]
        message = self._build_alert_message(question, analysis)
        return AgentResult(payload={"analysis": analysis, "alert_message": message})

    def _build_alert_message(self, question: str, analysis: dict[str, Any]) -> str:
        country_clause = ""
        if analysis.get("top_country"):
            country_clause = f" Top country driver: {analysis['top_country']}."
        return (
            f"Agentic Analytics Copilot alert: {question}. "
            f"Detected a {analysis['drop_percent']:.1f}% revenue drop.{country_clause} "
            f"Insight: {analysis['insight']}"
        )


class PrimaryCoordinatorAgent:
    def __init__(self, registry: ToolRegistry, sql_agent: SqlAgent, insight_agent: InsightAgent, settings: Settings) -> None:
        self.registry = registry
        self.sql_agent = sql_agent
        self.insight_agent = insight_agent
        self.settings = settings

    def run(self, question: str) -> WorkflowResponse:
        context = WorkflowContext(
            request_id=str(uuid4()),
            question=question,
            schema_context=build_schema_context(self.settings),
            alert_threshold_percent=self.settings.alert_threshold_percent,
        )
        heading = self._build_heading(question)
        include_sql = self._should_include_sql(question)
        sql_payload = self.sql_agent.run(question, context).payload
        sql = str(sql_payload["sql"])
        validation_payload = self.registry.invoke("validate_sql", {"sql": sql}, context)
        validation = SqlValidationResult(**validation_payload["validation"])

        if not validation.valid:
            context.add_step("execute_sql", "skipped", "SQL execution skipped because validation failed.")
            formatted_response = self._format_response(
                question=question,
                analysis=AnalysisResult(drop_percent=0.0, insight=validation.reason),
                rows=[],
                chart=ChartResult(mime_type="", base64_data=""),
                sql=sql,
                include_sql=include_sql,
            )
            return WorkflowResponse(
                heading=heading,
                sql=sql if include_sql else None,
                validation=validation,
                data_preview=[],
                analysis=AnalysisResult(drop_percent=0.0, insight=validation.reason),
                chart=ChartResult(mime_type="", base64_data=""),
                alert=AlertResult(triggered=False, delivered=False, message=None),
                formatted_response=formatted_response,
                steps=context.step_logs,
            )

        execution_payload = self.registry.invoke("execute_sql", {"query": sql}, context)
        rows = self._normalize_columns(list(execution_payload["rows"]))

        insight_payload = self.insight_agent.run(question, rows, context).payload
        analysis = AnalysisResult(**insight_payload["analysis"])

        chart_payload = self.registry.invoke("render_chart", {"data": rows, "question": question}, context)
        chart = ChartResult(**chart_payload["chart"])

        triggered = analysis.drop_percent > context.alert_threshold_percent
        delivered = False
        message: str | None = None
        if triggered:
            message = str(insight_payload["alert_message"])
            alert_payload = self.registry.invoke("send_alert", {"message": message}, context)
            delivered = bool(alert_payload["delivered"])
        else:
            context.add_step("send_alert", "skipped", "Alert threshold not reached.")

        chart = ChartResult(**chart_payload["chart"])
        formatted_response = self._format_response(
            question=question,
            analysis=analysis,
            rows=rows[:10],
            chart=chart,
            sql=sql,
            include_sql=include_sql,
        )

        return WorkflowResponse(
            heading=heading,
            sql=sql if include_sql else None,
            validation=validation,
            data_preview=rows[:10],
            analysis=analysis,
            chart=chart,
            alert=AlertResult(triggered=triggered, delivered=delivered, message=message),
            formatted_response=formatted_response,
            steps=context.step_logs,
        )

    def _should_include_sql(self, question: str) -> bool:
        return True

    def _normalize_columns(self, rows: list[dict]) -> list[dict]:
        """Map common SQL column aliases to the canonical names expected by analyze_rows."""
        if not rows:
            return rows
        keys = set(rows[0].keys())
        rename: dict[str, str] = {}
        if "date" not in keys:
            for alias in ("transaction_date", "order_date", "sale_date", "day", "date_key", "sales_date"):
                if alias in keys:
                    rename[alias] = "date"
                    break
        if "revenue" not in keys:
            for alias in ("daily_revenue", "total_revenue", "revenue_sum", "amount", "sales"):
                if alias in keys:
                    rename[alias] = "revenue"
                    break
        if not rename:
            return rows
        return [{rename.get(k, k): v for k, v in row.items()} for row in rows]

    def _format_response(
        self,
        question: str,
        analysis: AnalysisResult,
        rows: list[dict[str, Any]],
        chart: ChartResult,
        sql: str,
        include_sql: bool,
    ) -> str:
        title = self._build_heading(question)
        sections = [
            f"# {title}",
            "## Analysis",
            analysis.insight,
            "## Data",
            self._format_rows(rows),
        ]
        if chart.mime_type and chart.base64_data:
            sections.extend(["## Chart", f"![Chart](data:{chart.mime_type};base64,{chart.base64_data})"])
        if include_sql:
            sections.extend(["## SQL Used", f"```sql\n{sql}\n```"])
        return "\n\n".join(sections)

    def _build_heading(self, question: str) -> str:
        cleaned = " ".join(question.strip().split())
        if not cleaned:
            return "Analytics Result"
        return cleaned[:1].upper() + cleaned[1:]

    def _format_rows(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "No rows returned."
        columns = list(rows[0].keys())
        lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
        for row in rows:
            values = [str(row.get(column, "")) for column in columns]
            lines.append("| " + " | ".join(values) + " |")
        return "\n".join(lines)


class ProductivityAgent:
    def __init__(self, registry: ToolRegistry, settings: Settings) -> None:
        self.registry = registry
        self.settings = settings

    def run(self, prompt: str) -> ProductivityResult:
        context = WorkflowContext(
            request_id=str(uuid4()),
            question=prompt,
            schema_context="productivity_tools",
            alert_threshold_percent=self.settings.alert_threshold_percent,
        )
        intents = productivity_intent(prompt)
        actions: list[dict[str, Any]] = []

        if intents["create_event"]:
            start_time, end_time = parse_datetime_text(prompt)
            event_title = extract_event_title(prompt)
            payload = self.registry.invoke(
                "create_calendar_event",
                {"title": event_title, "start_time": start_time, "end_time": end_time, "details": prompt},
                context,
            )
            actions.append({"type": "calendar_event", "result": payload["event"]})

        if intents["create_task"]:
            task_title = extract_task_title(prompt)
            due_at, _ = parse_datetime_text(prompt)
            payload = self.registry.invoke(
                "create_task",
                {"title": task_title, "due_at": due_at, "priority": "medium"},
                context,
            )
            actions.append({"type": "task", "result": payload["task"]})

        if intents["create_note"]:
            note_title, content = extract_note_content(prompt)
            payload = self.registry.invoke(
                "create_note",
                {"title": note_title, "content": content, "tags": "general"},
                context,
            )
            actions.append({"type": "note", "result": payload["note"]})

        if intents["list_tasks"]:
            payload = self.registry.invoke("list_tasks", {"limit": 10}, context)
            actions.append({"type": "task_list", "result": payload["tasks"]})

        if intents["list_events"]:
            event_query = extract_event_query(prompt)
            if event_query:
                payload = self.registry.invoke("search_calendar_events", {"query": event_query, "limit": 10}, context)
            else:
                payload = self.registry.invoke("list_calendar_events", {"limit": 10}, context)
            actions.append({"type": "calendar_list", "result": payload["events"]})

        if intents["search_notes"]:
            note_query = extract_note_query(prompt)
            if note_query:
                payload = self.registry.invoke("search_notes", {"query": note_query, "limit": 10}, context)
            else:
                payload = self.registry.invoke("list_notes", {"limit": 10}, context)
            actions.append({"type": "note_search", "result": payload["notes"]})

        if intents["send_message"]:
            message = extract_slack_message(prompt)
            payload = self.registry.invoke("send_slack_message", {"message": message}, context)
            actions.append({"type": "slack_message", "result": {"message": message, "delivered": payload["delivered"]}})

        snapshot = {
            "tasks": self.registry.invoke("list_tasks", {"limit": 5}, context)["tasks"],
            "calendar_events": self.registry.invoke("list_calendar_events", {"limit": 5}, context)["events"],
            "notes": self.registry.invoke("list_notes", {"limit": 5}, context)["notes"],
        }
        if not actions:
            context.add_step("productivity_router", "skipped", "No task/calendar/note actions inferred from prompt.")
        summary = (
            f"Completed {len(actions)} productivity action(s). "
            f"Current snapshot: {len(snapshot['tasks'])} tasks, {len(snapshot['calendar_events'])} events, {len(snapshot['notes'])} notes."
        )
        return ProductivityResult(actions=actions, snapshot=snapshot, summary=summary, steps=context.step_logs)


class CopilotCoordinatorAgent:
    def __init__(self, analytics_coordinator: PrimaryCoordinatorAgent, productivity_agent: ProductivityAgent) -> None:
        self.analytics_coordinator = analytics_coordinator
        self.productivity_agent = productivity_agent

    def run(self, prompt: str) -> CopilotResponse:
        lowered = prompt.lower()
        intents = productivity_intent(prompt)
        productivity_needed = any(intents.values())
        analytics_needed = any(
            token in lowered
            for token in ["revenue", "sales", "country", "trend", "compare", "drop", "insight", "sql", "analytics"]
        )
        if productivity_needed and self._is_productivity_focused_prompt(lowered, intents):
            analytics_needed = False

        analytics_result: dict[str, Any] | None = None
        productivity_result: dict[str, Any] | None = None
        steps = []
        domains: list[str] = []

        if analytics_needed:
            analytics_workflow = self.analytics_coordinator.run(prompt)
            analytics = analytics_workflow.to_dict()
            analytics_result = analytics
            steps.extend(analytics_workflow.steps)
            domains.append("analytics")

        if productivity_needed:
            productivity_workflow = self.productivity_agent.run(prompt)
            productivity = productivity_workflow.to_dict()
            productivity_result = productivity
            steps.extend(productivity_workflow.steps)
            domains.append("productivity")

        if analytics_result is None and productivity_result is None:
            productivity_workflow = self.productivity_agent.run(f"save a note that {prompt}")
            productivity = productivity_workflow.to_dict()
            productivity_result = productivity
            steps.extend(productivity_workflow.steps)
            domains.append("productivity")

        summaries = []
        if analytics_result:
            summaries.append(analytics_result["analysis"]["insight"])
        if productivity_result:
            summaries.append(productivity_result["summary"])

        return CopilotResponse(
            domains=domains,
            summary=" ".join(summaries),
            analytics=analytics_result,
            productivity=productivity_result,
            steps=steps,
        )

    def _is_productivity_focused_prompt(self, lowered: str, intents: dict[str, bool]) -> bool:
        productivity_intent_only = any(intents.values())
        explicit_analytics = any(
            token in lowered for token in ["compare", "trend", "drop", "sql", "analysis", "analyze", "chart", "graph"]
        )
        return productivity_intent_only and not explicit_analytics
