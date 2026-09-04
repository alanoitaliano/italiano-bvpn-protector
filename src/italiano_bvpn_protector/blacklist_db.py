from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS blocked_ranges (
    source TEXT NOT NULL,
    start_ip INTEGER NOT NULL,
    end_ip INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocked_ranges_source ON blocked_ranges(source);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def replace_source(db_path: Path, source: str, ranges: list[tuple[int, int]]) -> None:
    """Atomically replace all stored ranges for one source (blocking; call via asyncio.to_thread)."""
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM blocked_ranges WHERE source = ?", (source,))
            conn.executemany(
                "INSERT INTO blocked_ranges (source, start_ip, end_ip) VALUES (?, ?, ?)",
                [(source, start, end) for start, end in ranges],
            )
    finally:
        conn.close()


def load_source(db_path: Path, source: str) -> list[tuple[int, int]]:
    """Load previously stored (start_ip, end_ip) ranges for one source, if any
    (blocking; call via asyncio.to_thread)."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT start_ip, end_ip FROM blocked_ranges WHERE source = ?", (source,)
        ).fetchall()
        return [(row[0], row[1]) for row in rows]
    finally:
        conn.close()
