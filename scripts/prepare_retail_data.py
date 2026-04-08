from __future__ import annotations

import argparse
import csv
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the Kaggle Online Retail dataset for BigQuery.")
    parser.add_argument("--input", required=True, help="Path to the raw Online Retail CSV file")
    parser.add_argument("--output-dir", required=True, help="Directory where the transformed CSVs will be written")
    parser.add_argument(
        "--drop-factor",
        type=float,
        default=0.6,
        help="Multiplier applied to revenue in the latest 7-day window to inject a visible decline",
    )
    return parser.parse_args()


def load_rows(input_path: Path) -> list[dict[str, object]]:
    cleaned_rows: list[dict[str, object]] = []
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with input_path.open("r", newline="", encoding=encoding) as handle:
                reader = csv.DictReader(handle)
                for raw_row in reader:
                    customer_id = (raw_row.get("CustomerID") or "").strip()
                    if not customer_id:
                        continue

                    stock_code = (raw_row.get("StockCode") or "").strip()
                    invoice_no = (raw_row.get("InvoiceNo") or "").strip()
                    description = (raw_row.get("Description") or "").strip()
                    invoice_date = (raw_row.get("InvoiceDate") or "").strip()
                    if not stock_code or not invoice_no or not description or not invoice_date:
                        continue

                    try:
                        quantity = int((raw_row.get("Quantity") or "0").strip())
                        unit_price = Decimal((raw_row.get("UnitPrice") or "0").strip())
                        order_date = datetime.strptime(invoice_date, "%m/%d/%Y %H:%M")
                    except (ValueError, InvalidOperation):
                        continue

                    if quantity <= 0 or unit_price <= 0:
                        continue

                    revenue = Decimal(quantity) * unit_price
                    if revenue <= 0:
                        continue

                    cleaned_rows.append(
                        {
                            "invoice_no": invoice_no,
                            "product_id": stock_code,
                            "customer_id": customer_id,
                            "order_date": order_date,
                            "quantity": quantity,
                            "unit_price": unit_price,
                            "revenue": revenue,
                            "country": (raw_row.get("Country") or "").strip(),
                            "description": description,
                        }
                    )
            return cleaned_rows
        except UnicodeDecodeError:
            cleaned_rows.clear()
            continue
    raise UnicodeDecodeError("dataset", b"", 0, 1, "Unable to decode CSV with supported encodings")
    return cleaned_rows


def inject_drop_signal(rows: list[dict[str, object]], drop_factor: float) -> None:
    if not rows:
        return
    latest_date = max(row["order_date"] for row in rows)
    window_start = latest_date - timedelta(days=6)
    for row in rows:
        if row["order_date"] >= window_start:
            row["revenue"] = (row["revenue"] * Decimal(str(drop_factor))).quantize(Decimal("0.01"))


def write_outputs(rows: list[dict[str, object]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    customers: OrderedDict[str, dict[str, str]] = OrderedDict()
    products: OrderedDict[str, dict[str, str]] = OrderedDict()

    transactions_path = output_dir / "transactions.csv"
    with transactions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "invoice_no",
                "product_id",
                "customer_id",
                "order_date",
                "quantity",
                "unit_price",
                "revenue",
            ],
        )
        writer.writeheader()
        for row in rows:
            customers.setdefault(str(row["customer_id"]), {"customer_id": str(row["customer_id"]), "country": str(row["country"])})
            products.setdefault(str(row["product_id"]), {"product_id": str(row["product_id"]), "description": str(row["description"])})
            writer.writerow(
                {
                    "invoice_no": row["invoice_no"],
                    "product_id": row["product_id"],
                    "customer_id": row["customer_id"],
                    "order_date": row["order_date"].isoformat(sep=" "),
                    "quantity": row["quantity"],
                    "unit_price": f"{row['unit_price']:.2f}",
                    "revenue": f"{row['revenue']:.2f}",
                }
            )

    with (output_dir / "customers.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["customer_id", "country"])
        writer.writeheader()
        writer.writerows(customers.values())

    with (output_dir / "products.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["product_id", "description"])
        writer.writeheader()
        writer.writerows(products.values())


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    rows = load_rows(input_path)
    inject_drop_signal(rows, args.drop_factor)
    write_outputs(rows, output_dir)
    print(f"Wrote {len(rows)} transactions to {output_dir}")


if __name__ == "__main__":
    main()
