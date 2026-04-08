from __future__ import annotations

import argparse
import importlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]


TABLES: tuple[TableSpec, ...] = (
    TableSpec("tasks", ("id", "title", "due_at", "status", "priority", "created_at")),
    TableSpec("calendar_events", ("id", "title", "start_time", "end_time", "location", "details", "created_at")),
    TableSpec("notes", ("id", "title", "content", "tags", "created_at")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate productivity data from SQLite to Postgres for tasks, calendar events, and notes."
    )
    parser.add_argument("--sqlite-path", required=True, help="Path to the source SQLite database file.")
    parser.add_argument("--postgres-dsn", required=True, help="Target Postgres DSN (postgresql://...).")
    parser.add_argument(
        "--truncate-target",
        action="store_true",
        help="Delete existing target table data before inserting migrated rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and count rows from SQLite without writing to Postgres.",
    )
    return parser.parse_args()


def fetch_rows(sqlite_path: str, spec: TableSpec) -> list[tuple]:
    with sqlite3.connect(sqlite_path) as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT {', '.join(spec.columns)} FROM {spec.name} ORDER BY id")
        return cur.fetchall()


def create_target_tables(pg_conn: Any) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                due_at TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'medium',
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_events (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                location TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id BIGSERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def truncate_tables(pg_conn: Any) -> None:
    with pg_conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE tasks, calendar_events, notes RESTART IDENTITY")


def upsert_rows(pg_conn: Any, spec: TableSpec, rows: list[tuple]) -> None:
    if not rows:
        return

    column_list = ", ".join(spec.columns)
    placeholders = ", ".join(["%s"] * len(spec.columns))
    updates = ", ".join([f"{col} = EXCLUDED.{col}" for col in spec.columns if col != "id"])

    sql = (
        f"INSERT INTO {spec.name} ({column_list}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )
    with pg_conn.cursor() as cur:
        cur.executemany(sql, rows)


def reset_sequence(pg_conn: Any, table_name: str) -> None:
    if table_name not in {spec.name for spec in TABLES}:
        raise ValueError(f"Unsupported table for sequence reset: {table_name}")

    with pg_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence(%s, 'id'),
                GREATEST(COALESCE((SELECT MAX(id) FROM {table_name}), 0), 1),
                COALESCE((SELECT MAX(id) FROM {table_name}), 0) > 0
            )
            """,
            (table_name,),
        )


def load_psycopg() -> Any:
    try:
        return importlib.import_module("psycopg")
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required for Postgres migration. Install with: pip install -e '.[cloud]'") from exc


def main() -> None:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    table_rows: dict[str, list[tuple]] = {}
    for spec in TABLES:
        table_rows[spec.name] = fetch_rows(str(sqlite_path), spec)

    total = sum(len(rows) for rows in table_rows.values())
    print(f"Read {total} total row(s) from {sqlite_path}")
    for spec in TABLES:
        print(f"- {spec.name}: {len(table_rows[spec.name])}")

    if args.dry_run:
        print("Dry run complete; no Postgres writes performed.")
        return

    psycopg = load_psycopg()

    with psycopg.connect(args.postgres_dsn) as pg_conn:
        create_target_tables(pg_conn)
        if args.truncate_target:
            truncate_tables(pg_conn)
        for spec in TABLES:
            upsert_rows(pg_conn, spec, table_rows[spec.name])
            reset_sequence(pg_conn, spec.name)
        pg_conn.commit()

    print("Migration complete.")


if __name__ == "__main__":
    main()
