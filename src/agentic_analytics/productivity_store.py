from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote_plus


class ProductivityStore:
    def __init__(
        self,
        db_path: str,
        backend: str = "sqlite",
        postgres_dsn: str | None = None,
    ) -> None:
        self.backend = backend
        self.db_path = db_path
        self.postgres_dsn = postgres_dsn
        self._psycopg = None
        if self.backend == "postgres":
            self._psycopg = self._load_psycopg()
        self._initialize()

    def _load_psycopg(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional cloud dependency
            raise RuntimeError("Postgres support requires `psycopg`. Install with `pip install -e \".[cloud]\"`.") from exc
        return psycopg

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if self.backend == "postgres":
            if not self.postgres_dsn:
                raise RuntimeError("POSTGRES_DSN or DATABASE_URL must be set when PRODUCTIVITY_STORE_BACKEND=postgres.")
            conn = self._psycopg.connect(self.postgres_dsn)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
            return

        db_parent = Path(self.db_path).expanduser().resolve().parent
        db_parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        if self.backend == "postgres":
            self._initialize_postgres()
            return
        self._initialize_sqlite()

    def _initialize_sqlite(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    due_at TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    priority TEXT NOT NULL DEFAULT 'medium',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    location TEXT,
                    details TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _initialize_postgres(self) -> None:
        with self.connection() as conn:
            with conn.cursor() as cur:
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

    def create_task(self, title: str, due_at: str | None = None, priority: str = "medium") -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        if self.backend == "postgres":
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO tasks (title, due_at, status, priority, created_at)
                        VALUES (%s, %s, 'open', %s, %s)
                        RETURNING id
                        """,
                        (title, due_at, priority, created_at),
                    )
                    task_id = cur.fetchone()[0]
        else:
            with self.connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO tasks (title, due_at, status, priority, created_at) VALUES (?, ?, 'open', ?, ?)",
                    (title, due_at, priority, created_at),
                )
                task_id = cursor.lastrowid
        return {"id": task_id, "title": title, "due_at": due_at, "status": "open", "priority": priority}

    def list_tasks(self, status: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if self.backend == "postgres":
            query = "SELECT id, title, due_at, status, priority, created_at FROM tasks"
            params: list[Any] = []
            if status:
                query += " WHERE status = %s"
                params.append(status)
            query += " ORDER BY COALESCE(due_at, created_at), id DESC LIMIT %s"
            params.append(limit)
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    columns = [desc.name for desc in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in rows]

        query = "SELECT id, title, due_at, status, priority, created_at FROM tasks"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY COALESCE(due_at, created_at), id DESC LIMIT ?"
        params += (limit,)
        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def create_calendar_event(
        self,
        title: str,
        start_time: str,
        end_time: str | None = None,
        location: str | None = None,
        details: str | None = None,
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        if self.backend == "postgres":
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO calendar_events (title, start_time, end_time, location, details, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (title, start_time, end_time, location, details, created_at),
                    )
                    event_id = cur.fetchone()[0]
        else:
            with self.connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO calendar_events (title, start_time, end_time, location, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (title, start_time, end_time, location, details, created_at),
                )
                event_id = cursor.lastrowid
        return {
            "id": event_id,
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "location": location,
            "details": details,
        }

    def list_calendar_events(self, limit: int = 10) -> list[dict[str, Any]]:
        if self.backend == "postgres":
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, title, start_time, end_time, location, details, created_at
                        FROM calendar_events
                        ORDER BY start_time ASC, id DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    rows = cur.fetchall()
                    columns = [desc.name for desc in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in rows]

        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, start_time, end_time, location, details, created_at
                FROM calendar_events
                ORDER BY start_time ASC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_calendar_events(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        like = f"%{query}%"
        if self.backend == "postgres":
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, title, start_time, end_time, location, details, created_at
                        FROM calendar_events
                        WHERE title ILIKE %s OR COALESCE(location, '') ILIKE %s OR COALESCE(details, '') ILIKE %s
                        ORDER BY start_time ASC, id DESC
                        LIMIT %s
                        """,
                        (like, like, like, limit),
                    )
                    rows = cur.fetchall()
                    columns = [desc.name for desc in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in rows]

        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, start_time, end_time, location, details, created_at
                FROM calendar_events
                WHERE title LIKE ? OR COALESCE(location, '') LIKE ? OR COALESCE(details, '') LIKE ?
                ORDER BY start_time ASC, id DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_note(self, title: str, content: str, tags: str | None = None) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        if self.backend == "postgres":
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO notes (title, content, tags, created_at)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                        """,
                        (title, content, tags, created_at),
                    )
                    note_id = cur.fetchone()[0]
        else:
            with self.connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO notes (title, content, tags, created_at) VALUES (?, ?, ?, ?)",
                    (title, content, tags, created_at),
                )
                note_id = cursor.lastrowid
        return {"id": note_id, "title": title, "content": content, "tags": tags}

    def search_notes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        like = f"%{query}%"
        if self.backend == "postgres":
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, title, content, tags, created_at
                        FROM notes
                        WHERE title ILIKE %s OR content ILIKE %s OR COALESCE(tags, '') ILIKE %s
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        (like, like, like, limit),
                    )
                    rows = cur.fetchall()
                    columns = [desc.name for desc in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in rows]

        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, content, tags, created_at
                FROM notes
                WHERE title LIKE ? OR content LIKE ? OR COALESCE(tags, '') LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def snapshot(self, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
        return {
            "tasks": self.list_tasks(limit=limit),
            "calendar_events": self.list_calendar_events(limit=limit),
            "notes": self.search_notes("", limit=limit),
        }


def build_postgres_dsn(
    *,
    user: str,
    password: str,
    database: str,
    host: str | None = None,
    port: int | None = None,
) -> str:
    if not host:
        host = "127.0.0.1"
    port_fragment = f":{port}" if port else ""
    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}{port_fragment}/{quote_plus(database)}"
