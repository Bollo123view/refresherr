"""
History module - Event logging for broken symlinks.

This module provides backward-compatible functions for event logging.
All actual database logic is now handled by the central db module.
"""
import os, sqlite3, time
from typing import Iterable
from .core import db

def _db_path() -> str:
    """Get database path - kept for backward compatibility."""
    base = os.environ.get("DATA_DIR", "/data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "symlinks.db")

def _ensure():
    """Ensure schema - now handled by central DB module."""
    conn = db.get_connection(_db_path())
    db.initialize_schema(conn)
    conn.close()

def add_events(rows: Iterable[tuple]):
    """
    Add event records - delegates to central DB module.
    
    Args:
        rows: Iterable of tuples (ts, path, target, kind, name, action, status)
    """
    db.add_events(list(rows))
