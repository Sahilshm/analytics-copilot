from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load prepared retail CSV files into BigQuery.")
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument("--dataset", required=True, help="BigQuery dataset name")
    parser.add_argument("--location", default="US", help="BigQuery location")
    parser.add_argument("--transactions", required=True, help="Path to transactions.csv")
    parser.add_argument("--customers", required=True, help="Path to customers.csv")
    parser.add_argument("--products", required=True, help="Path to products.csv")
    return parser.parse_args()


def ensure_dataset(client, dataset_id: str, location: str) -> None:
    from google.cloud import bigquery

    dataset = bigquery.Dataset(dataset_id)
    dataset.location = location
    client.create_dataset(dataset, exists_ok=True)


def load_csv(client, table_id: str, source_path: Path, schema) -> None:
    from google.cloud import bigquery

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    with source_path.open("rb") as handle:
        job = client.load_table_from_file(handle, table_id, job_config=job_config)
    job.result()


def main() -> None:
    args = parse_args()
    try:
        from google.cloud import bigquery
    except ImportError as exc:
        raise SystemExit("Install cloud dependencies first: pip install -e \".[cloud]\"") from exc

    client = bigquery.Client(project=args.project, location=args.location)
    dataset_id = f"{args.project}.{args.dataset}"
    ensure_dataset(client, dataset_id, args.location)

    load_csv(
        client,
        f"{dataset_id}.transactions",
        Path(args.transactions),
        [
            bigquery.SchemaField("invoice_no", "STRING"),
            bigquery.SchemaField("product_id", "STRING"),
            bigquery.SchemaField("customer_id", "STRING"),
            bigquery.SchemaField("order_date", "TIMESTAMP"),
            bigquery.SchemaField("quantity", "INTEGER"),
            bigquery.SchemaField("unit_price", "FLOAT"),
            bigquery.SchemaField("revenue", "FLOAT"),
        ],
    )
    load_csv(
        client,
        f"{dataset_id}.customers",
        Path(args.customers),
        [
            bigquery.SchemaField("customer_id", "STRING"),
            bigquery.SchemaField("country", "STRING"),
        ],
    )
    load_csv(
        client,
        f"{dataset_id}.products",
        Path(args.products),
        [
            bigquery.SchemaField("product_id", "STRING"),
            bigquery.SchemaField("description", "STRING"),
        ],
    )
    print(f"Loaded dataset {dataset_id} in {args.location}")


if __name__ == "__main__":
    main()
