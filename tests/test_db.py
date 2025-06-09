import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src import database


def test_init_db(tmp_path):
    db_path = tmp_path / "test.db"
    os_environ_backup = database.os.environ.get("DATABASE_PATH")
    database.os.environ["DATABASE_PATH"] = str(db_path)
    try:
        database.init_db()
        assert db_path.exists()
    finally:
        if os_environ_backup is None:
            del database.os.environ["DATABASE_PATH"]
        else:
            database.os.environ["DATABASE_PATH"] = os_environ_backup
