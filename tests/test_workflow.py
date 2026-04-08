from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_analytics.config import Settings
from agentic_analytics.service import build_service


class WorkflowTests(TestCase):
    def test_end_to_end_drop_workflow_triggers_alert(self) -> None:
        settings = Settings(
            llm_backend="rule_based",
            warehouse_backend="demo",
            notifier_backend="log",
            demo_anchor_date="2026-04-06",
        )
        service = build_service(settings)
        result = service.ask("Which country contributed most to revenue drop?")
        self.assertEqual(result["analysis"]["top_country"], "United Kingdom")
        self.assertGreater(result["analysis"]["drop_percent"], 20.0)
        self.assertTrue(result["alert"]["triggered"])
        self.assertTrue(result["alert"]["delivered"])
        self.assertGreaterEqual(len(result["steps"]), 5)

    def test_country_comparison_query_returns_steps(self) -> None:
        settings = Settings(demo_anchor_date="2026-04-06")
        service = build_service(settings)
        result = service.ask("Compare this week vs last week revenue by country")
        self.assertEqual(result["alert"]["triggered"], True)
        self.assertIn("country", result["data_preview"][0])
        self.assertEqual(result["steps"][0]["tool"], "generate_sql")

    def test_response_includes_validation_and_formatted_sections(self) -> None:
        settings = Settings(demo_anchor_date="2026-04-06")
        service = build_service(settings)
        result = service.ask("Show me sales for last month")
        self.assertEqual(result["heading"], "Show me sales for last month")
        self.assertTrue(result["validation"]["valid"])
        self.assertIsNone(result["sql"])
        self.assertIn("# Show me sales for last month", result["formatted_response"])
        self.assertIn("## Analysis", result["formatted_response"])
        self.assertIn("## Data", result["formatted_response"])
        self.assertNotIn("## SQL Used", result["formatted_response"])

    def test_formatted_response_includes_sql_only_when_requested(self) -> None:
        settings = Settings(demo_anchor_date="2026-04-06")
        service = build_service(settings)
        result = service.ask("Show me sales for this year and show SQL used")
        self.assertIsNotNone(result["sql"])
        self.assertIn("## SQL Used", result["formatted_response"])
        self.assertIn("```sql", result["formatted_response"])
