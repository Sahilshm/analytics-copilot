from __future__ import annotations

from .config import Settings


def build_schema_context(settings: Settings) -> str:
    return f"""
Retail Analytics Database Schema with Join Instructions for Dynamic SQL Generation:

=== PRIMARY FACT TABLE ===

1. {settings.table_ref(settings.transactions_table)} (Daily transaction-level records)
   Columns:
   - invoice_no: STRING (unique transaction identifier)
   - product_id: STRING (FOREIGN KEY → products.product_id)
   - customer_id: STRING (FOREIGN KEY → customers.customer_id)
   - order_date: TIMESTAMP (when transaction occurred)
   - quantity: INTEGER (units purchased)
   - unit_price: FLOAT (price per unit)
   - revenue: FLOAT (calculated as quantity × unit_price)
   
   Data Range: 2011-2026 (historical + backfilled 2026 data)
   Primary Use Cases: Daily trends, customer analysis, product performance
   
   Default Join Pattern (Use when user asks about products OR countries):
   SELECT t.*, p.description, c.country
   FROM {settings.table_ref(settings.transactions_table)} t
   LEFT JOIN {settings.table_ref(settings.products_table)} p ON t.product_id = p.product_id
   LEFT JOIN {settings.table_ref(settings.customers_table)} c ON t.customer_id = c.customer_id

=== DIMENSION TABLES ===

2. {settings.table_ref(settings.customers_table)} (Customer master data)
   Columns:
   - customer_id: STRING (PRIMARY KEY)
   - country: STRING (customer's country for geographic segmentation)
   
   Primary Use Cases: Country-level revenue analysis, geographic comparisons
   
   Join Condition:
   transactions.customer_id = customers.customer_id (for country-level queries)
   sales.customer_id = customers.customer_id (for sales-based geographic analysis)

3. {settings.table_ref(settings.products_table)} (Product master data)
   Columns:
   - product_id: STRING (PRIMARY KEY)
   - description: STRING (product name/title for human-readable reports)
   
   Primary Use Cases: Top products by revenue, product-level trends, product descriptions
   
   Join Condition:
   transactions.product_id = products.product_id (for product-level analysis)
   sales.product_id = products.product_id (for sales-based product category analysis)

=== AGGREGATED FACT TABLE ===

4. {settings.table_ref(settings.sales_table)} (Aggregated sales data for trend analysis)
   Columns:
   - sale_id: STRING (unique sale record identifier)
   - sale_date: DATE (aggregated date, use for trends)
   - customer_id: STRING (FOREIGN KEY → customers.customer_id)
   - product_id: STRING (FOREIGN KEY → products.product_id)
   - region: STRING (sales region/territory)
   - product_category: STRING (product category grouping)
   - units_sold: INTEGER (total units in period)
   - revenue: FLOAT (total revenue)
   - profit_margin: FLOAT (profit percentage, 0-100)
   
   Data Range: 2011-2026 (includes backfilled 2026 data)
   Primary Use Cases: Multi-year trends, profit analysis, category-level summaries
   
   When to use sales vs transactions:
   - USE SALES TABLE for: multi-year trends, profit margin queries, category analysis
   - USE TRANSACTIONS TABLE for: daily detail, customer-level analysis, recent data

=== RECOMMENDED JOIN PATTERNS ===

PATTERN 1: Revenue by Product (Top N Products)
SELECT 
  p.description,
  SUM(t.revenue) AS total_revenue,
  SUM(t.quantity) AS total_units
FROM {settings.table_ref(settings.transactions_table)} t
JOIN {settings.table_ref(settings.products_table)} p ON t.product_id = p.product_id
WHERE DATE(t.order_date) BETWEEN '2026-01-01' AND '2026-03-31'
GROUP BY t.product_id, p.description
ORDER BY total_revenue DESC
LIMIT 5

PATTERN 2: Revenue by Country (Geographic Analysis)
SELECT 
  c.country,
  SUM(t.revenue) AS total_revenue,
  COUNT(DISTINCT t.customer_id) AS customer_count
FROM {settings.table_ref(settings.transactions_table)} t
JOIN {settings.table_ref(settings.customers_table)} c ON t.customer_id = c.customer_id
WHERE DATE(t.order_date) BETWEEN '2026-01-01' AND '2026-03-31'
GROUP BY c.country
ORDER BY total_revenue DESC

PATTERN 3: Product by Country (Two Join Tables)
SELECT 
  c.country,
  p.description,
  SUM(t.revenue) AS total_revenue
FROM {settings.table_ref(settings.transactions_table)} t
JOIN {settings.table_ref(settings.products_table)} p ON t.product_id = p.product_id
JOIN {settings.table_ref(settings.customers_table)} c ON t.customer_id = c.customer_id
WHERE DATE(t.order_date) BETWEEN '2026-01-01' AND '2026-03-31'
GROUP BY c.country, p.product_id, p.description
ORDER BY c.country, total_revenue DESC

PATTERN 4: Time Series with Product Details (Date Grouping)
SELECT 
  FORMAT_DATE('%Y-%m', DATE(t.order_date)) AS month,
  p.description,
  SUM(t.revenue) AS monthly_revenue,
  SUM(t.quantity) AS monthly_units
FROM {settings.table_ref(settings.transactions_table)} t
JOIN {settings.table_ref(settings.products_table)} p ON t.product_id = p.product_id
WHERE DATE(t.order_date) BETWEEN '2026-01-01' AND '2026-03-31'
GROUP BY month, p.product_id, p.description
ORDER BY month DESC, monthly_revenue DESC

PATTERN 5: Time Series by Country (Geographic Trends)
SELECT 
  DATE(t.order_date) AS date,
  c.country,
  SUM(t.revenue) AS daily_revenue
FROM {settings.table_ref(settings.transactions_table)} t
JOIN {settings.table_ref(settings.customers_table)} c ON t.customer_id = c.customer_id
WHERE DATE(t.order_date) BETWEEN '2026-01-01' AND '2026-03-31'
GROUP BY date, c.country
ORDER BY date DESC, daily_revenue DESC

=== CRITICAL BUSINESS RULES FOR SQL GENERATION ===

TIME-BASED QUERIES:
- When user mentions months (Jan, Feb, Mar) or quarters → ALWAYS include date/month column in SELECT
- ALWAYS GROUP BY the date/month column for time-series queries
- Use FORMAT_DATE('%Y-%m', DATE(order_date)) for month grouping in BigQuery
- Use DATE(column) for daily grouping, FORMAT_DATE for month/year grouping
- Date range filtering: WHERE DATE(order_date) >= '2026-01-01' AND DATE(order_date) <= '2026-03-31'

PRODUCT QUERIES:
- User mentions "products", "items", "what sold" → JOIN products table mandatory
- Always include product description in SELECT for readability
- Group by product_id AND p.description together
- Example trigger phrases: "which products", "top products", "by product"

GEOGRAPHIC QUERIES:
- User mentions "country", "region", "countries by" → JOIN customers table mandatory
- Always include customer.country in SELECT when geographic analysis requested
- Group by c.country for country-level aggregations
- Example trigger phrases: "by country", "countries", "region", "geographic"

MULTI-TABLE JOINS:
- If query asks for BOTH products AND countries → use all three tables (transactions + products + customers)
- Maintain table aliases: t=transactions, p=products, c=customers for clarity
- Example: "Show revenue by country and product for Q1 2026" → needs both JOIN conditions

DATE AGGREGATION:
- Month/Year queries require: FORMAT_DATE/EXTRACT and GROUP BY month column
- Include the month column in SELECT for column-based pivoting in charts
- Example columns: FORMAT_DATE('%Y-%m', ...) AS month, EXTRACT(MONTH FROM ...) AS month_num

CHART-FRIENDLY OUTPUT:
- For time-series charts: Include date/month column + numeric column (revenue, units, etc.)
- For categorical charts: Include category column + numeric series (product, country, etc.)
- Example: SELECT product AS category, revenue_jan, revenue_feb, revenue_mar (for side-by-side comparison)
- Alternative: SELECT product, month, revenue (for pivoting in chart renderer)

=== DATA QUALITY NOTES ===

Missing Dates: Check that order_date ranges from 2011 to 2026 (backfilled 2025-2026 data)
Domain Tables: Products table has 600+ unique products, Customers table has 5000+ unique customers
Data Freshness: Transactions data is refreshed daily, sales data is refreshed monthly
Null Values: customer_id and product_id should not be NULL in transactions table

=== VERTEX AI LLM INSTRUCTIONS ===

You are generating BigQuery SQL for retail analytics queries. Use ONLY the tables, columns, and join patterns above.
Always include proper JOIN conditions from the patterns provided.
Always group by all non-aggregated columns to avoid GROUP BY errors.
For multi-month queries, always include the month/date column in SELECT and GROUP BY.
Generate valid BigQuery SQL with correct syntax and proper formatting.
""".strip()


def schema_overview(settings: Settings) -> dict[str, object]:
    return {
        "warehouse_backend": settings.warehouse_backend,
        "sql_dialect": settings.sql_dialect,
        "tables": {
            "transactions": {
                "name": settings.table_ref(settings.transactions_table),
                "columns": [
                    "invoice_no",
                    "product_id",
                    "customer_id",
                    "order_date",
                    "quantity",
                    "unit_price",
                    "revenue",
                ],
            },
            "customers": {
                "name": settings.table_ref(settings.customers_table),
                "columns": ["customer_id", "country"],
            },
            "products": {
                "name": settings.table_ref(settings.products_table),
                "columns": ["product_id", "description"],
            },
            "sales": {
                "name": settings.table_ref(settings.sales_table),
                "columns": [
                    "sale_id",
                    "sale_date",
                    "customer_id",
                    "product_id",
                    "region",
                    "product_category",
                    "units_sold",
                    "revenue",
                    "profit_margin",
                ],
            },
        },
        "relationships": [
            "transactions.customer_id -> customers.customer_id",
            "transactions.product_id -> products.product_id",
            "sales.customer_id -> customers.customer_id",
            "sales.product_id -> products.product_id",
        ],
        "tools": [
            "generate_sql",
            "execute_sql",
            "analyze_data",
            "render_chart",
            "send_alert",
        ],
    }
