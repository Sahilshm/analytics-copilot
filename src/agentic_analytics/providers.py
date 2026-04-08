from __future__ import annotations

import base64
import json
import logging
import math
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any
from urllib import request

from .config import Settings
from .domain import ChartResult

LOGGER = logging.getLogger(__name__)


class LLMClient(ABC):
    @abstractmethod
    def generate_sql(self, question: str, schema_context: str) -> str:
        raise NotImplementedError


class WarehouseClient(ABC):
    dialect: str

    @abstractmethod
    def query(self, sql: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def validate_query(self, sql: str) -> tuple[bool, str]:
        raise NotImplementedError


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str) -> bool:
        raise NotImplementedError


class ChartRenderer(ABC):
    @abstractmethod
    def render(self, rows: list[dict[str, Any]], question: str) -> ChartResult:
        raise NotImplementedError


class RuleBasedLLMClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_sql(self, question: str, schema_context: str) -> str:
        normalized = " ".join(question.lower().split())
        if any(token in normalized for token in ["by month, year", "by month year", "by month and year"]):
            return self._sales_by_month_year_sql()
        if "last month" in normalized and any(token in normalized for token in ["sales", "revenue"]):
            return self._last_month_sales_sql()
        if "this year" in normalized and any(token in normalized for token in ["sales", "revenue"]):
            return self._this_year_sales_sql()
        if "country" in normalized and ("drop" in normalized or "decline" in normalized):
            return self._country_drop_sql()
        if "compare" in normalized and "country" in normalized:
            return self._country_period_sql()
        if "product" in normalized:
            return self._product_revenue_sql()
        return self._trend_sql()

    def _last_month_sales_sql(self) -> str:
        transactions = self.settings.table_ref(self.settings.transactions_table)
        if self.settings.sql_dialect == "bigquery":
            return f"""
-- SALES_LAST_MONTH
WITH latest_date AS (
  SELECT MAX(DATE(order_date)) AS max_order_date
  FROM {transactions}
),
month_window AS (
  SELECT
    DATE_TRUNC(DATE_SUB(max_order_date, INTERVAL 1 MONTH), MONTH) AS last_month_start,
    DATE_SUB(DATE_TRUNC(max_order_date, MONTH), INTERVAL 1 DAY) AS last_month_end
  FROM latest_date
)
SELECT
  DATE(t.order_date) AS date,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
CROSS JOIN month_window
WHERE DATE(t.order_date) BETWEEN month_window.last_month_start AND month_window.last_month_end
GROUP BY date
ORDER BY date
""".strip()
        return f"""
-- SALES_LAST_MONTH
SELECT
  DATE(t.order_date) AS date,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
WHERE strftime('%Y-%m', DATE(t.order_date)) = strftime('%Y-%m', DATE('now', '-1 month'))
GROUP BY DATE(t.order_date)
ORDER BY date
""".strip()

    def _this_year_sales_sql(self) -> str:
        transactions = self.settings.table_ref(self.settings.transactions_table)
        if self.settings.sql_dialect == "bigquery":
            return f"""
-- SALES_THIS_YEAR
WITH latest_date AS (
  SELECT MAX(DATE(order_date)) AS max_order_date
  FROM {transactions}
)
SELECT
  FORMAT_DATE('%Y-%m', DATE(t.order_date)) AS month,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
CROSS JOIN latest_date
WHERE EXTRACT(YEAR FROM DATE(t.order_date)) = EXTRACT(YEAR FROM latest_date.max_order_date)
GROUP BY month
ORDER BY month
""".strip()
        return f"""
-- SALES_THIS_YEAR
SELECT
  strftime('%Y-%m', DATE(t.order_date)) AS month,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
WHERE strftime('%Y', DATE(t.order_date)) = strftime('%Y', DATE('now'))
GROUP BY month
ORDER BY month
""".strip()

    def _sales_by_month_year_sql(self) -> str:
        transactions = self.settings.table_ref(self.settings.transactions_table)
        if self.settings.sql_dialect == "bigquery":
            return f"""
-- SALES_BY_MONTH_YEAR
SELECT
  FORMAT_DATE('%Y-%m', DATE(t.order_date)) AS month,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
GROUP BY month
ORDER BY month
""".strip()
        return f"""
-- SALES_BY_MONTH_YEAR
SELECT
  strftime('%Y-%m', DATE(t.order_date)) AS month,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
GROUP BY month
ORDER BY month
""".strip()

    def _trend_sql(self) -> str:
        transactions = self.settings.table_ref(self.settings.transactions_table)
        if self.settings.sql_dialect == "bigquery":
            return f"""
WITH latest_date AS (
  SELECT MAX(DATE(order_date)) AS max_order_date
  FROM {transactions}
)
SELECT
  DATE(t.order_date) AS date,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
CROSS JOIN latest_date
WHERE DATE(t.order_date) BETWEEN DATE_SUB(latest_date.max_order_date, INTERVAL 13 DAY) AND latest_date.max_order_date
GROUP BY date
ORDER BY date
""".strip()
        return f"""
SELECT
  DATE(t.order_date) AS date,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
GROUP BY DATE(t.order_date)
ORDER BY date
""".strip()

    def _country_period_sql(self) -> str:
        transactions = self.settings.table_ref(self.settings.transactions_table)
        customers = self.settings.table_ref(self.settings.customers_table)
        if self.settings.sql_dialect == "bigquery":
            return f"""
WITH latest_date AS (
  SELECT MAX(DATE(order_date)) AS max_order_date
  FROM {transactions}
),
labeled AS (
  SELECT
    c.country AS country,
    CASE
      WHEN DATE(t.order_date) BETWEEN DATE_SUB(latest_date.max_order_date, INTERVAL 6 DAY) AND latest_date.max_order_date THEN 'last_7_days'
      WHEN DATE(t.order_date) BETWEEN DATE_SUB(latest_date.max_order_date, INTERVAL 13 DAY) AND DATE_SUB(latest_date.max_order_date, INTERVAL 7 DAY) THEN 'previous_7_days'
      ELSE NULL
    END AS period,
    t.revenue AS revenue
  FROM {transactions} AS t
  CROSS JOIN latest_date
  JOIN {customers} AS c
    ON t.customer_id = c.customer_id
  WHERE DATE(t.order_date) BETWEEN DATE_SUB(latest_date.max_order_date, INTERVAL 13 DAY) AND latest_date.max_order_date
)
SELECT
  country,
  period,
  ROUND(SUM(revenue), 2) AS revenue
FROM labeled
WHERE period IS NOT NULL
GROUP BY country, period
ORDER BY country, period
""".strip()
        return f"""
WITH labeled AS (
  SELECT
    c.country AS country,
    CASE
      WHEN DATE(t.order_date) >= DATE('now', '-6 day') THEN 'last_7_days'
      WHEN DATE(t.order_date) >= DATE('now', '-13 day') AND DATE(t.order_date) < DATE('now', '-6 day') THEN 'previous_7_days'
      ELSE NULL
    END AS period,
    t.revenue AS revenue
  FROM {transactions} AS t
  JOIN {customers} AS c
    ON t.customer_id = c.customer_id
)
SELECT
  country,
  period,
  ROUND(SUM(revenue), 2) AS revenue
FROM labeled
WHERE period IS NOT NULL
GROUP BY country, period
ORDER BY country, period
""".strip()

    def _country_drop_sql(self) -> str:
        transactions = self.settings.table_ref(self.settings.transactions_table)
        customers = self.settings.table_ref(self.settings.customers_table)
        if self.settings.sql_dialect == "bigquery":
            return f"""
WITH latest_date AS (
  SELECT MAX(DATE(order_date)) AS max_order_date
  FROM {transactions}
),
country_period_revenue AS (
  SELECT
    c.country AS country,
    SUM(
      CASE
        WHEN DATE(t.order_date) BETWEEN DATE_SUB(latest_date.max_order_date, INTERVAL 6 DAY) AND latest_date.max_order_date
        THEN t.revenue ELSE 0
      END
    ) AS last_7_days_revenue,
    SUM(
      CASE
        WHEN DATE(t.order_date) BETWEEN DATE_SUB(latest_date.max_order_date, INTERVAL 13 DAY) AND DATE_SUB(latest_date.max_order_date, INTERVAL 7 DAY)
        THEN t.revenue ELSE 0
      END
    ) AS previous_7_days_revenue
  FROM {transactions} AS t
  CROSS JOIN latest_date
  JOIN {customers} AS c
    ON t.customer_id = c.customer_id
  WHERE DATE(t.order_date) BETWEEN DATE_SUB(latest_date.max_order_date, INTERVAL 13 DAY) AND latest_date.max_order_date
  GROUP BY c.country
)
SELECT
  country,
  ROUND(previous_7_days_revenue, 2) AS previous_7_days_revenue,
  ROUND(last_7_days_revenue, 2) AS last_7_days_revenue,
  ROUND(last_7_days_revenue - previous_7_days_revenue, 2) AS revenue_delta
FROM country_period_revenue
ORDER BY revenue_delta ASC, previous_7_days_revenue DESC
""".strip()
        return f"""
WITH country_period_revenue AS (
  SELECT
    c.country AS country,
    SUM(CASE WHEN DATE(t.order_date) >= DATE('now', '-6 day') THEN t.revenue ELSE 0 END) AS last_7_days_revenue,
    SUM(CASE WHEN DATE(t.order_date) >= DATE('now', '-13 day') AND DATE(t.order_date) < DATE('now', '-6 day') THEN t.revenue ELSE 0 END) AS previous_7_days_revenue
  FROM {transactions} AS t
  JOIN {customers} AS c
    ON t.customer_id = c.customer_id
  GROUP BY c.country
)
SELECT
  country,
  ROUND(previous_7_days_revenue, 2) AS previous_7_days_revenue,
  ROUND(last_7_days_revenue, 2) AS last_7_days_revenue,
  ROUND(last_7_days_revenue - previous_7_days_revenue, 2) AS revenue_delta
FROM country_period_revenue
ORDER BY revenue_delta ASC, previous_7_days_revenue DESC
""".strip()

    def _product_revenue_sql(self) -> str:
        transactions = self.settings.table_ref(self.settings.transactions_table)
        products = self.settings.table_ref(self.settings.products_table)
        return f"""
SELECT
  p.description,
  ROUND(SUM(t.revenue), 2) AS revenue
FROM {transactions} AS t
JOIN {products} AS p
  ON t.product_id = p.product_id
GROUP BY p.description
ORDER BY revenue DESC
LIMIT 10
""".strip()


class VertexLLMClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_sql(self, question: str, schema_context: str) -> str:
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
        except ImportError as exc:
            raise RuntimeError("Vertex AI dependencies are not installed. Install with `pip install -e \".[cloud]\"`.") from exc

        vertexai.init(project=self.settings.gcp_project_id, location=self.settings.vertex_location)
        prompt = (
            "You are a senior analytics SQL planner. "
            "Return only executable SQL for BigQuery. No markdown fences, no explanation.\n\n"
            f"{schema_context}\n\n"
            f"Question: {question}"
        )
        model = GenerativeModel(self.settings.vertex_model)
        response = model.generate_content(prompt)
        sql = getattr(response, "text", "").strip()
        if not sql:
            raise RuntimeError("Vertex AI returned an empty SQL response.")
        return sql.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()


class BigQueryWarehouseClient(WarehouseClient):
    dialect = "bigquery"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise RuntimeError("BigQuery dependencies are not installed. Install with `pip install -e \".[cloud]\"`.") from exc
        self._bigquery = bigquery
        self._client = bigquery.Client(project=settings.gcp_project_id, location=settings.bigquery_location)

    def query(self, sql: str) -> list[dict[str, Any]]:
        rows = self._client.query(sql).result()
        return [self._normalize_row(dict(row.items())) for row in rows]

    def validate_query(self, sql: str) -> tuple[bool, str]:
        cleaned = sql.strip()
        normalized = cleaned.lower()
        if any(token in f" {normalized} " for token in [" insert ", " update ", " delete ", " merge ", " drop ", " alter ", " truncate "]):
            return False, "Mutation statements are not allowed."
        if not normalized.startswith(("select", "with", "--")):
            return False, "Only read-only SELECT queries are allowed."
        try:
            job_config = self._bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
            self._client.query(cleaned, job_config=job_config)
        except Exception as exc:
            return False, str(exc)
        return True, "SQL validated successfully with a BigQuery dry run."

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                normalized[key] = float(value)
            elif isinstance(value, (datetime, date)):
                normalized[key] = value.isoformat()
            else:
                normalized[key] = value
        return normalized


class DemoWarehouseClient(WarehouseClient):
    dialect = "sqlite"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.anchor_date = date.fromisoformat(settings.demo_anchor_date)
        (
            self.daily_totals,
            self.country_period,
            self.country_drop,
            self.last_month_sales,
            self.this_year_sales,
            self.sales_by_month_year,
        ) = self._build_demo_data()

    def query(self, sql: str) -> list[dict[str, Any]]:
        normalized = " ".join(sql.lower().split())
        if "sales_last_month" in normalized:
            return [dict(row) for row in self.last_month_sales]
        if "sales_this_year" in normalized:
            return [dict(row) for row in self.this_year_sales]
        if "sales_by_month_year" in normalized:
            return [dict(row) for row in self.sales_by_month_year]
        if "previous_7_days_revenue" in normalized or "revenue_delta" in normalized:
            return [dict(row) for row in self.country_drop]
        if "period" in normalized and "country" in normalized:
            return [dict(row) for row in self.country_period]
        return [dict(row) for row in self.daily_totals]

    def validate_query(self, sql: str) -> tuple[bool, str]:
        normalized = f" {sql.lower()} "
        blocked_tokens = [" insert ", " update ", " delete ", " merge ", " drop ", " alter ", " truncate "]
        if any(token in normalized for token in blocked_tokens):
            return False, "Mutation statements are not allowed in demo mode."
        if not sql.strip().lower().startswith(("select", "with", "--")):
            return False, "Only read-only SELECT queries are allowed."
        return True, "SQL validated successfully in demo mode."

    def _build_demo_data(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        previous_values = [1200.0, 1260.0, 1310.0, 1295.0, 1360.0, 1420.0, 1480.0]
        last_values = [760.0, 810.0, 780.0, 795.0, 840.0, 860.0, 885.0]
        start = self.anchor_date - timedelta(days=13)
        daily: list[dict[str, Any]] = []
        for offset, value in enumerate(previous_values + last_values):
            current = start + timedelta(days=offset)
            daily.append({"date": current.isoformat(), "revenue": round(value, 2)})

        last_month_start = (self.anchor_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        last_month_sales: list[dict[str, Any]] = []
        for offset in range(30):
            current = last_month_start + timedelta(days=offset)
            revenue = 900.0 + ((offset % 5) * 55.0) + (offset * 3.0)
            last_month_sales.append({"date": current.isoformat(), "revenue": round(revenue, 2)})

        this_year_sales = [
            {"month": f"{self.anchor_date.year}-01", "revenue": 18240.0},
            {"month": f"{self.anchor_date.year}-02", "revenue": 19510.0},
            {"month": f"{self.anchor_date.year}-03", "revenue": 20180.0},
            {"month": f"{self.anchor_date.year}-04", "revenue": 8845.0},
        ]
        sales_by_month_year = [
            {"month": "2025-11", "revenue": 12640.0},
            {"month": "2025-12", "revenue": 14120.0},
            {"month": f"{self.anchor_date.year}-01", "revenue": 18240.0},
            {"month": f"{self.anchor_date.year}-02", "revenue": 19510.0},
            {"month": f"{self.anchor_date.year}-03", "revenue": 20180.0},
            {"month": f"{self.anchor_date.year}-04", "revenue": 8845.0},
        ]

        country_previous = {
            "United Kingdom": 4100.0,
            "Netherlands": 2400.0,
            "Germany": 1825.0,
        }
        country_last = {
            "United Kingdom": 2300.0,
            "Netherlands": 1605.0,
            "Germany": 825.0,
        }

        period_rows: list[dict[str, Any]] = []
        delta_rows: list[dict[str, Any]] = []
        for country in country_previous:
            period_rows.append({"country": country, "period": "previous_7_days", "revenue": country_previous[country]})
            period_rows.append({"country": country, "period": "last_7_days", "revenue": country_last[country]})
            delta_rows.append(
                {
                    "country": country,
                    "previous_7_days_revenue": country_previous[country],
                    "last_7_days_revenue": country_last[country],
                    "revenue_delta": round(country_last[country] - country_previous[country], 2),
                }
            )
        delta_rows.sort(key=lambda row: (row["revenue_delta"], -row["previous_7_days_revenue"]))
        return daily, period_rows, delta_rows, last_month_sales, this_year_sales, sales_by_month_year


class LogNotifier(Notifier):
    def send(self, message: str) -> bool:
        LOGGER.info("Alert triggered: %s", message)
        return True


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, message: str) -> bool:
        payload = json.dumps({"text": message}).encode("utf-8")
        req = request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as response:
            return 200 <= response.status < 300


class MatplotlibChartRenderer(ChartRenderer):
    def render(self, rows: list[dict[str, Any]], question: str) -> ChartResult:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise RuntimeError("matplotlib is not installed.") from exc

        fig, ax = plt.subplots(figsize=(9, 4.5))
        keys = set(rows[0].keys()) if rows else set()
        if {"date", "revenue"}.issubset(keys):
            dates = [row["date"] for row in rows]
            revenue = [float(row["revenue"]) for row in rows]
            ax.plot(dates, revenue, marker="o", color="#1d4ed8")
            ax.set_xlabel("Date")
            ax.set_ylabel("Revenue")
        else:
            categories, series = _pivot_chart_data(rows)
            num_series = len(series)
            if num_series > 0:
                width = 0.8 / num_series
                positions = list(range(len(categories)))
                colors = ["#2563eb", "#f97316", "#16a34a", "#dc2626", "#8b5cf6", "#0ea5e9"]
                for index, (series_name, values) in enumerate(series.items()):
                    offset = (index - num_series / 2.0 + 0.5) * width
                    x_positions = [position + offset for position in positions]
                    ax.bar(x_positions, values, width=width, label=str(series_name), color=colors[index % len(colors)])
                ax.set_xticks(positions, categories)
                ax.legend()
        ax.set_title(question)
        ax.grid(alpha=0.2)
        fig.autofmt_xdate(rotation=35)
        buffer = BytesIO()
        fig.tight_layout()
        fig.savefig(buffer, format="png")
        plt.close(fig)
        return ChartResult(mime_type="image/png", base64_data=base64.b64encode(buffer.getvalue()).decode("utf-8"))


class SvgChartRenderer(ChartRenderer):
    def render(self, rows: list[dict[str, Any]], question: str) -> ChartResult:
        svg = _render_svg_chart(rows, question)
        return ChartResult(
            mime_type="image/svg+xml",
            base64_data=base64.b64encode(svg.encode("utf-8")).decode("utf-8"),
        )


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_backend == "vertex":
        return VertexLLMClient(settings)
    return RuleBasedLLMClient(settings)


def build_warehouse_client(settings: Settings) -> WarehouseClient:
    if settings.warehouse_backend == "bigquery":
        return BigQueryWarehouseClient(settings)
    return DemoWarehouseClient(settings)


def build_notifier(settings: Settings) -> Notifier:
    if settings.notifier_backend == "slack" and settings.slack_webhook_url:
        return SlackNotifier(settings.slack_webhook_url)
    return LogNotifier()


def build_chart_renderer() -> ChartRenderer:
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        return SvgChartRenderer()
    return MatplotlibChartRenderer()


def _pivot_chart_data(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[float]]]:
    if rows and {"month", "revenue"}.issubset(rows[0]):
        months = [str(row["month"]) for row in rows]
        series = {"revenue": [float(row["revenue"]) for row in rows]}
        return months, series

    if rows and {"country", "period", "revenue"}.issubset(rows[0]):
        countries = sorted({str(row["country"]) for row in rows})
        periods = sorted({str(row["period"]) for row in rows})
        series = {period: [] for period in periods}
        lookup = {(str(row["country"]), str(row["period"])): float(row["revenue"]) for row in rows}
        for country in countries:
            for period in periods:
                series[period].append(lookup.get((country, period), 0.0))
        return countries, series

    # Generic fallback: first non-numeric column as category, all numeric columns as series
    if not rows:
        return [], {}
        
    row_keys = list(rows[0].keys())
    cat_keys = [k for k in row_keys if isinstance(rows[0][k], str)]
    cat_key = cat_keys[0] if cat_keys else row_keys[0]
    
    num_keys = [k for k in row_keys if isinstance(rows[0][k], (int, float)) or str(rows[0][k]).replace('.','',1).isdigit()]
    if not num_keys:
        num_keys = [k for k in row_keys if k != cat_key]

    categories = [str(row.get(cat_key, "")) for row in rows]
    series = {}
    for k in num_keys:
        try:
            series[k] = [float(row.get(k, 0.0) or 0.0) for row in rows]
        except (ValueError, TypeError):
            continue

    return categories, series


def _render_svg_chart(rows: list[dict[str, Any]], question: str) -> str:
    width = 900
    height = 420
    plot_left = 70
    plot_top = 50
    plot_width = width - 120
    plot_height = height - 120
    keys = set(rows[0].keys()) if rows else set()
    title = question.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    elements: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff" />',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-size="20" font-family="Arial" fill="#0f172a">{title}</text>',
        f'<rect x="{plot_left}" y="{plot_top}" width="{plot_width}" height="{plot_height}" fill="#f8fafc" stroke="#cbd5e1" />',
    ]

    if {"date", "revenue"}.issubset(keys):
        revenue = [float(row["revenue"]) for row in rows] or [0.0]
        max_value = max(revenue) or 1.0
        points: list[str] = []
        label_elements: list[str] = []
        for index, row in enumerate(rows):
            x = plot_left + (plot_width * index / max(1, len(rows) - 1))
            y = plot_top + plot_height - ((float(row["revenue"]) / max_value) * (plot_height - 20))
            points.append(f"{x:.2f},{y:.2f}")
            label_y = plot_top + plot_height + 18
            label_elements.append(
                f'<text x="{x:.2f}" y="{label_y}" text-anchor="middle" font-size="10" font-family="Arial" fill="#475569">{row["date"]}</text>'
            )
        elements.append(
            f'<polyline fill="none" stroke="#2563eb" stroke-width="3" points="{" ".join(points)}" />'
        )
        for point in points:
            x, y = point.split(",")
            elements.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#2563eb" />')
        elements.extend(label_elements)
    else:
        categories, series = _pivot_chart_data(rows)
        max_value = max((value for values in series.values() for value in values), default=1.0) or 1.0
        bar_group_width = plot_width / max(1, len(categories))
        bar_width = max(20.0, (bar_group_width / max(1, len(series))) - 12.0)
        colors = ["#2563eb", "#f97316", "#16a34a"]
        for group_index, category in enumerate(categories):
            label_x = plot_left + group_index * bar_group_width + (bar_group_width / 2)
            safe_category = category.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            elements.append(
                f'<text x="{label_x:.2f}" y="{plot_top + plot_height + 22}" text-anchor="middle" font-size="11" font-family="Arial" fill="#475569">{safe_category}</text>'
            )
            for series_index, (series_name, values) in enumerate(series.items()):
                value = values[group_index]
                bar_height = (value / max_value) * (plot_height - 30)
                x = plot_left + group_index * bar_group_width + 10 + series_index * (bar_width + 8)
                y = plot_top + plot_height - bar_height
                elements.append(
                    f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" fill="{colors[series_index % len(colors)]}" rx="3" />'
                )
                elements.append(
                    f'<text x="{x + (bar_width / 2):.2f}" y="{y - 6:.2f}" text-anchor="middle" font-size="10" font-family="Arial" fill="#334155">{value:.0f}</text>'
                )

    for tick_index in range(5):
        value = tick_index / 4
        y = plot_top + plot_height - value * plot_height
        elements.append(f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_left + plot_width}" y2="{y:.2f}" stroke="#e2e8f0" />')

    elements.append("</svg>")
    return "".join(elements)
