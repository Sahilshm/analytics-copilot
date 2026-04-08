from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Settings:
    app_name: str = "Agentic Analytics Copilot"
    app_env: str = "development"
    llm_backend: str = "rule_based"
    warehouse_backend: str = "demo"
    notifier_backend: str = "log"
    alert_threshold_percent: float = 20.0
    gcp_project_id: str | None = None
    bigquery_dataset: str = "analytics_copilot"
    bigquery_location: str = "US"
    vertex_location: str = "us-central1"
    vertex_model: str = "gemini-2.5-flash"
    slack_webhook_url: str | None = None
    demo_anchor_date: str = date.today().isoformat()
    transactions_table: str = "transactions"
    customers_table: str = "customers"
    products_table: str = "products"
    sales_table: str = "sales"
    productivity_store_backend: str = "sqlite"
    sqlite_db_path: str = "./copilot.db"
    postgres_dsn: str | None = None

    @property
    def sql_dialect(self) -> str:
        return "bigquery" if self.warehouse_backend == "bigquery" else "sqlite"

    def table_ref(self, table_name: str) -> str:
        if self.warehouse_backend == "bigquery" and self.gcp_project_id:
            return f"`{self.gcp_project_id}.{self.bigquery_dataset}.{table_name}`"
        return table_name

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            llm_backend=os.getenv("LLM_BACKEND", "rule_based"),
            warehouse_backend=os.getenv("WAREHOUSE_BACKEND", "demo"),
            notifier_backend=os.getenv("NOTIFIER_BACKEND", "log"),
            alert_threshold_percent=float(os.getenv("ALERT_THRESHOLD_PERCENT", "20")),
            gcp_project_id=os.getenv("GCP_PROJECT_ID") or None,
            bigquery_dataset=os.getenv("BIGQUERY_DATASET", "analytics_copilot"),
            bigquery_location=os.getenv("BIGQUERY_LOCATION", "US"),
            vertex_location=os.getenv("VERTEX_LOCATION", "us-central1"),
            vertex_model=os.getenv("VERTEX_MODEL", "gemini-2.5-flash"),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL") or None,
            demo_anchor_date=os.getenv("DEMO_ANCHOR_DATE", date.today().isoformat()),
            transactions_table=os.getenv("TRANSACTIONS_TABLE", "transactions"),
            customers_table=os.getenv("CUSTOMERS_TABLE", "customers"),
            products_table=os.getenv("PRODUCTS_TABLE", "products"),
            sales_table=os.getenv("SALES_TABLE", "sales"),
            productivity_store_backend=os.getenv("PRODUCTIVITY_STORE_BACKEND", "sqlite"),
            sqlite_db_path=os.getenv("SQLITE_DB_PATH", "./copilot.db"),
            postgres_dsn=os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL") or None,
        )
