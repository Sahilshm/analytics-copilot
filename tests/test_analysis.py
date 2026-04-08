from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_analytics.tools import analyze_rows, calculate_drop_percent


class AnalysisTests(TestCase):
    def test_calculate_drop_percent_returns_positive_drop(self) -> None:
        self.assertEqual(calculate_drop_percent(100.0, 60.0), 40.0)
        self.assertEqual(calculate_drop_percent(0.0, 60.0), 0.0)
        self.assertEqual(calculate_drop_percent(100.0, 120.0), 0.0)

    def test_analyze_rows_for_country_drop_shape(self) -> None:
        rows = [
            {
                "country": "United Kingdom",
                "previous_7_days_revenue": 4100.0,
                "last_7_days_revenue": 2300.0,
                "revenue_delta": -1800.0,
            },
            {
                "country": "Germany",
                "previous_7_days_revenue": 1825.0,
                "last_7_days_revenue": 825.0,
                "revenue_delta": -1000.0,
            },
        ]
        analysis = analyze_rows(rows)
        self.assertAlmostEqual(analysis.drop_percent, 47.26, places=2)
        self.assertEqual(analysis.top_country, "United Kingdom")
        self.assertIn("United Kingdom", analysis.insight)

    def test_analyze_rows_for_trend_shape(self) -> None:
        rows = []
        for index, revenue in enumerate([100, 110, 120, 130, 140, 150, 160, 80, 85, 90, 88, 92, 95, 98]):
            rows.append({"date": f"2026-04-{index + 1:02d}", "revenue": revenue})
        analysis = analyze_rows(rows)
        self.assertGreater(analysis.drop_percent, 20)
        self.assertIn("latest 7 days", analysis.insight)

    def test_analyze_rows_for_last_month_sales(self) -> None:
        rows = [
            {"date": "2026-03-01", "revenue": 100.0},
            {"date": "2026-03-02", "revenue": 180.0},
            {"date": "2026-03-03", "revenue": 150.0},
        ]
        analysis = analyze_rows(rows, "Show me sales for last month")
        self.assertEqual(analysis.drop_percent, 0.0)
        self.assertIn("Total sales for last month", analysis.insight)
        self.assertIn("2026-03-02", analysis.insight)

    def test_analyze_rows_for_this_year_sales(self) -> None:
        rows = [
            {"month": "2026-01", "revenue": 1000.0},
            {"month": "2026-02", "revenue": 1400.0},
            {"month": "2026-03", "revenue": 1200.0},
        ]
        analysis = analyze_rows(rows, "Show me sales for this year")
        self.assertEqual(analysis.drop_percent, 0.0)
        self.assertIn("Total sales for this year", analysis.insight)
        self.assertIn("2026-02", analysis.insight)

    def test_analyze_rows_for_sales_by_month_year(self) -> None:
        rows = [
            {"month": "2025-12", "revenue": 900.0},
            {"month": "2026-01", "revenue": 1100.0},
            {"month": "2026-02", "revenue": 1500.0},
        ]
        analysis = analyze_rows(rows, "Show me sales by month, year")
        self.assertEqual(analysis.drop_percent, 0.0)
        self.assertIn("Sales grouped by month-year", analysis.insight)
        self.assertIn("2026-02", analysis.insight)
