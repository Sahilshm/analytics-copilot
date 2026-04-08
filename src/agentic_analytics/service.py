from __future__ import annotations

import logging
from dataclasses import dataclass

from .agents import CopilotCoordinatorAgent, InsightAgent, PrimaryCoordinatorAgent, ProductivityAgent, SqlAgent
from .config import Settings
from .providers import build_chart_renderer, build_llm_client, build_notifier, build_warehouse_client
from .productivity_store import ProductivityStore
from .productivity_tools import (
    CreateCalendarEventTool,
    CreateNoteTool,
    CreateTaskTool,
    ListNotesTool,
    ListCalendarEventsTool,
    ListTasksTool,
    SearchCalendarEventsTool,
    SearchNotesTool,
)
from .schema import schema_overview
from .tools import AnalyzeDataTool, ExecuteSQLTool, GenerateSQLTool, RenderChartTool, SendAlertTool, SendSlackMessageTool, ToolRegistry, ValidateSQLTool


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@dataclass
class AppService:
    settings: Settings
    coordinator: PrimaryCoordinatorAgent
    copilot_coordinator: CopilotCoordinatorAgent
    registry: ToolRegistry

    def ask(self, question: str) -> dict[str, object]:
        return self.coordinator.run(question).to_dict()

    def copilot(self, prompt: str) -> dict[str, object]:
        return self.copilot_coordinator.run(prompt).to_dict()

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "environment": self.settings.app_env,
            "providers": {
                "llm": self.settings.llm_backend,
                "warehouse": self.settings.warehouse_backend,
                "notifier": self.settings.notifier_backend,
            },
        }

    def schema(self) -> dict[str, object]:
        overview = schema_overview(self.settings)
        overview["tool_specs"] = self.registry.list_tools()
        return overview


def build_service(settings: Settings | None = None) -> AppService:
    configure_logging()
    resolved_settings = settings or Settings.from_env()
    llm = build_llm_client(resolved_settings)
    warehouse = build_warehouse_client(resolved_settings)
    notifier = build_notifier(resolved_settings)
    chart_renderer = build_chart_renderer()
    productivity_store = ProductivityStore(
        db_path=resolved_settings.sqlite_db_path,
        backend=resolved_settings.productivity_store_backend,
        postgres_dsn=resolved_settings.postgres_dsn,
    )

    registry = ToolRegistry(
        tools=[
            GenerateSQLTool(llm),
            ValidateSQLTool(warehouse),
            ExecuteSQLTool(warehouse),
            AnalyzeDataTool(),
            RenderChartTool(chart_renderer),
            SendAlertTool(notifier),
            SendSlackMessageTool(notifier),
            CreateTaskTool(productivity_store),
            ListTasksTool(productivity_store),
            CreateCalendarEventTool(productivity_store),
            ListCalendarEventsTool(productivity_store),
            SearchCalendarEventsTool(productivity_store),
            CreateNoteTool(productivity_store),
            ListNotesTool(productivity_store),
            SearchNotesTool(productivity_store),
        ]
    )
    sql_agent = SqlAgent(registry)
    insight_agent = InsightAgent(registry)
    coordinator = PrimaryCoordinatorAgent(registry, sql_agent, insight_agent, resolved_settings)
    productivity_agent = ProductivityAgent(registry, resolved_settings)
    copilot_coordinator = CopilotCoordinatorAgent(coordinator, productivity_agent)
    return AppService(
        settings=resolved_settings,
        coordinator=coordinator,
        copilot_coordinator=copilot_coordinator,
        registry=registry,
    )
