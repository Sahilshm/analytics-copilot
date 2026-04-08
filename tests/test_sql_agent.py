from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_analytics.config import Settings
from agentic_analytics.providers import RuleBasedLLMClient
from agentic_analytics.schema import build_schema_context


class SqlAgentTests(TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            llm_backend="rule_based",
            warehouse_backend="bigquery",
            gcp_project_id="demo-project",
            bigquery_dataset="analytics_copilot",
        )
        self.client = RuleBasedLLMClient(self.settings)
        self.schema_context = build_schema_context(self.settings)

    def test_generates_country_drop_sql(self) -> None:
        sql = self.client.generate_sql("Which country contributed most to revenue drop?", self.schema_context)
        self.assertIn("previous_7_days_revenue", sql)
        self.assertIn("JOIN `demo-project.analytics_copilot.customers`", sql)

    def test_generates_country_comparison_sql(self) -> None:
        sql = self.client.generate_sql("Compare this week vs last week revenue by country", self.schema_context)
        self.assertIn("period", sql)
        self.assertIn("GROUP BY country, period", sql)

    def test_generates_trend_sql(self) -> None:
        sql = self.client.generate_sql("Show last 7 days revenue trend", self.schema_context)
        self.assertIn("GROUP BY date", sql)
        self.assertIn("ORDER BY date", sql)

    def test_generates_last_month_sales_sql(self) -> None:
        sql = self.client.generate_sql("Show me sales for last month", self.schema_context)
        self.assertIn("SALES_LAST_MONTH", sql)
        self.assertIn("GROUP BY date", sql)

    def test_generates_this_year_sales_sql(self) -> None:
        sql = self.client.generate_sql("Show me sales for this year", self.schema_context)
        self.assertIn("SALES_THIS_YEAR", sql)
        self.assertIn("GROUP BY month", sql)

    def test_generates_sales_by_month_year_sql(self) -> None:
        sql = self.client.generate_sql("Show me sales by month, year", self.schema_context)
        self.assertIn("SALES_BY_MONTH_YEAR", sql)
        self.assertIn("GROUP BY month", sql)
