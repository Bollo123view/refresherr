import os, sqlite3, time
from typing import Iterable

def _db_path() -> str:
    base = os.environ.get("DATA_DIR", "/data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "history.db")

def _ensure():
    with sqlite3.connect(_db_path()) as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            path TEXT NOT NULL,
            target TEXT,
            kind TEXT,
            name TEXT,
            action TEXT,
            status TEXT
        )
        """)
        db.commit()

def add_events(rows: Iterable[tuple]):
    _ensure()
    with sqlite3.connect(_db_path()) as db:
        db.executemany(
            "INSERT INTO events (ts, path, target, kind, name, action, status) VALUES (?,?,?,?,?,?,?)",
            rows
        )
        db.commit()
