"""Database access for the Campus Customs MCP server.

Every tool in this server reads through this module. There is exactly one source of
data (the SQLite working copy) and exactly one source of "today" (the `desk` table),
so no tool can invent a value or drift onto the real system clock.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

# mcp_server/ lives directly under the HW 5 root, next to data/ and output/.
HW5_ROOT = Path(__file__).resolve().parent.parent

# The working copy, not the pristine data pack. Later tasks write to this file;
# the three tools in this server only read from it.
DEFAULT_DB = HW5_ROOT / "data" / "campus_customs_new.db"


def db_path() -> Path:
    """Resolve the database file, honouring the CAMPUS_CUSTOMS_DB override."""
    override = os.environ.get("CAMPUS_CUSTOMS_DB")
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_DB


def connect() -> sqlite3.Connection:
    """Open the working-copy database with row access by column name."""
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Campus Customs database not found at {path}. "
            "Run Task 2 to create data/campus_customs_new.db, or set CAMPUS_CUSTOMS_DB."
        )
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def today(con: sqlite3.Connection) -> date:
    """The dataset's current date, read from `desk.date_today`.

    This snapshot is dated 2026-08-31. Using the real system clock here would make
    every overdue/upcoming judgement wrong, so the date is always read from the
    database and never defaulted.
    """
    row = con.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None or not row["date_today"]:
        raise RuntimeError(
            "The `desk` table has no date_today value, so the current date is unknown. "
            "Refusing to guess."
        )
    return date.fromisoformat(row["date_today"])


def money(value: float) -> float:
    """Round a currency amount to cents without changing its source."""
    return round(float(value), 2)
