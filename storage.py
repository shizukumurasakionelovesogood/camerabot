from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = "camera_controller.sqlite3"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    path = Path(db_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_id INTEGER,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT
            )
            """
        )
        conn.commit()


def log_command(
    user_id: int | None,
    command: str,
    status: str,
    details: str = "",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO command_logs (created_at, user_id, command, status, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (utc_now_iso(), user_id, command, status, details),
        )
        conn.commit()


def get_last_command(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT created_at, user_id, command, status, details
            FROM command_logs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    return dict(row) if row else None
