import os
import sqlite3
from pathlib import Path


def _db_path() -> Path:
    """Return the current database path."""
    return Path(os.getenv("DATABASE_PATH", "database.db"))


def init_db():
    """Create the database and a basic members table if it doesn't exist."""
    db_path = _db_path()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dues INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_connection():
    """Return a connection to the database."""
    db_path = _db_path()
    if not db_path.exists():
        init_db()
    return sqlite3.connect(db_path)
