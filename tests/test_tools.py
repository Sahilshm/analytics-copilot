from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_analytics.config import Settings
from agentic_analytics.domain import WorkflowContext
from agentic_analytics.providers import DemoWarehouseClient, LogNotifier, RuleBasedLLMClient, SvgChartRenderer
from agentic_analytics.schema import build_schema_context
from agentic_analytics.tools import AnalyzeDataTool, ExecuteSQLTool, GenerateSQLTool, RenderChartTool, SendAlertTool, ToolRegistry, ValidateSQLTool


class ToolRegistryTests(TestCase):
    def setUp(self) -> None:
        settings = Settings()
        self.context = WorkflowContext(
            request_id="test-request",
            question="Show last 7 days revenue trend",
            schema_context=build_schema_context(settings),
            alert_threshold_percent=20.0,
        )
        self.registry = ToolRegistry(
            [
                GenerateSQLTool(RuleBasedLLMClient(settings)),
                ValidateSQLTool(DemoWarehouseClient(settings)),
                ExecuteSQLTool(DemoWarehouseClient(settings)),
                AnalyzeDataTool(),
                RenderChartTool(SvgChartRenderer()),
                SendAlertTool(LogNotifier()),
            ]
        )

    def test_registry_validates_missing_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.invoke("generate_sql", {}, self.context)

    def test_render_chart_tool_returns_base64_payload(self) -> None:
        rows = [{"date": "2026-04-01", "revenue": 100.0}, {"date": "2026-04-02", "revenue": 80.0}]
        result = self.registry.invoke("render_chart", {"data": rows, "question": "Trend"}, self.context)
        self.assertEqual(result["chart"]["mime_type"], "image/svg+xml")
        self.assertTrue(result["chart"]["base64_data"])

    def test_validate_sql_tool_rejects_mutation(self) -> None:
        result = self.registry.invoke("validate_sql", {"sql": "DELETE FROM transactions"}, self.context)
        self.assertFalse(result["validation"]["valid"])
        self.assertIn("not allowed", result["validation"]["reason"].lower())
