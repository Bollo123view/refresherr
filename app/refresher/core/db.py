"""
Central database module for Refresherr.

This module provides a single source of truth for database connections and schema
management. All database access should go through this module to ensure consistency.

Schema Overview:
- schema_version: Tracks the current schema version
- symlinks: Tracks symlink paths, targets, and status (broken/ok)
- actions: Queues repair/search actions (URLs to invoke via relay)
- movies: Radarr movie metadata
- movie_files: Radarr movie file metadata and symlink paths
- series: Sonarr series metadata
- episode_files: Sonarr episode file metadata and symlink paths
- events: Historical event log for broken symlinks

Schema Version History:
- v1: Initial schema with all tables
"""

from __future__ import annotations
import os
import sqlite3
import datetime as dt
import threading
from typing import Optional

# Current schema version
SCHEMA_VERSION = 1

# Database path from environment or default
DEFAULT_DB = os.path.join(os.environ.get("DATA_DIR", "/data"), "symlinks.db")

# Thread-safe lock for database operations
_db_lock = threading.Lock()


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Get a database connection with proper configuration.
    
    Args:
        db_path: Path to database file. If None, uses DEFAULT_DB from environment.
        
    Returns:
        Configured SQLite connection with row_factory set to sqlite3.Row.
    """
    path = db_path or DEFAULT_DB
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


def _create_schema_version_table(conn: sqlite3.Connection):
    """Create the schema_version table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            applied_utc TEXT NOT NULL
        )
    """)
    conn.commit()


def _create_v1_schema(conn: sqlite3.Connection):
    """
    Create version 1 schema.
    
    Tables created:
    - symlinks: Tracks symlink paths and their status
    - actions: Queues repair actions
    - movies: Radarr movie metadata
    - movie_files: Radarr movie file metadata
    - series: Sonarr series metadata
    - episode_files: Sonarr episode file metadata
    - events: Historical event log
    """
    cur = conn.cursor()
    
    # Symlinks table - tracks all scanned symlinks
    cur.execute("""
        CREATE TABLE IF NOT EXISTS symlinks (
            path TEXT PRIMARY KEY,
            last_target TEXT,
            status TEXT,
            last_status TEXT,
            first_seen_utc TEXT,
            last_seen_utc TEXT
        )
    """)
    # Note: Both 'status' and 'last_status' columns exist for backward compatibility.
    # New code should use 'last_status' as the canonical status field.
    
    # Actions table - queues repair/search actions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            reason TEXT,
            related_path TEXT,
            created_utc TEXT,
            fired_utc TEXT,
            last_error TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_related_path ON actions(related_path)")
    
    # Movies table - Radarr movie metadata
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY,
            instance TEXT,
            radarr_id INTEGER,
            title TEXT,
            year INTEGER,
            imdb_id TEXT,
            tmdb_id INTEGER,
            monitored INTEGER,
            added_utc TEXT,
            poster_url TEXT,
            fanart_url TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_movies_instance ON movies(instance)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_movies_instance_radarr ON movies(instance, radarr_id)")
    
    # Movie files table - Radarr movie file metadata
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movie_files (
            id INTEGER PRIMARY KEY,
            instance TEXT,
            radarr_movie_id INTEGER,
            radarr_file_id INTEGER,
            quality TEXT,
            resolution INTEGER,
            video_codec TEXT,
            audio_codec TEXT,
            size_bytes INTEGER,
            original_path TEXT,
            symlink_path TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_movie_files_inst_mid ON movie_files(instance, radarr_movie_id)")
    
    # Series table - Sonarr series metadata
    cur.execute("""
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY,
            instance TEXT,
            sonarr_id INTEGER,
            title TEXT,
            imdb_id TEXT,
            tvdb_id INTEGER,
            tmdb_id INTEGER,
            monitored INTEGER,
            poster_url TEXT,
            fanart_url TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_series_instance ON series(instance)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_series_instance_sid ON series(instance, sonarr_id)")
    
    # Episode files table - Sonarr episode file metadata
    cur.execute("""
        CREATE TABLE IF NOT EXISTS episode_files (
            id INTEGER PRIMARY KEY,
            instance TEXT,
            sonarr_series_id INTEGER,
            sonarr_file_id INTEGER,
            season_number INTEGER,
            quality TEXT,
            resolution INTEGER,
            release_group TEXT,
            size_bytes INTEGER,
            original_path TEXT,
            symlink_path TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_episode_files_inst_sid ON episode_files(instance, sonarr_series_id)")
    
    # Events table - historical event log
    cur.execute("""
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
    
    conn.commit()


def initialize_schema(conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
    """
    Initialize or upgrade the database schema to the current version.
    
    This function:
    1. Creates the schema_version table if it doesn't exist
    2. Checks the current schema version
    3. Applies any necessary migrations to reach SCHEMA_VERSION
    
    Args:
        conn: Optional existing connection. If None, creates a new one.
        
    Returns:
        The database connection (either the one passed in or newly created).
    """
    if conn is None:
        conn = get_connection()
    
    _create_schema_version_table(conn)
    current_version = _get_current_version(conn)
    
    if current_version < SCHEMA_VERSION:
        # Apply migrations
        if current_version < 1:
            _create_v1_schema(conn)
            conn.execute(
                "INSERT INTO schema_version (version, applied_utc) VALUES (?, ?)",
                (1, dt.datetime.utcnow().isoformat())
            )
            conn.commit()
            current_version = 1
        
        # Future migrations would go here:
        # if current_version < 2:
        #     _migrate_v1_to_v2(conn)
        #     conn.execute(...)
        #     current_version = 2
    
    return conn


def nuke_database(conn: Optional[sqlite3.Connection] = None, confirm: bool = False):
    """
    Drop all tables and reinitialize the database schema.
    
    WARNING: This will delete ALL data in the database!
    
    Args:
        conn: Optional existing connection. If None, creates a new one.
        confirm: Safety flag. Must be True to actually execute.
        
    Raises:
        ValueError: If confirm is not True.
    """
    if not confirm:
        raise ValueError("Must pass confirm=True to nuke_database(). This will delete all data!")
    
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    
    try:
        cur = conn.cursor()
        
        # Get all table names
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        
        # Drop all tables
        for table in tables:
            if table != 'sqlite_sequence':  # Don't drop SQLite internal table
                cur.execute(f"DROP TABLE IF EXISTS {table}")
        
        conn.commit()
        
        # Reinitialize schema
        initialize_schema(conn)
        
    finally:
        if close_after:
            conn.close()


# Backward compatibility helpers - these wrap the core functions
# to maintain the existing API used by store.py and other modules

def record_symlink(path: str, target: str | None, status: str):
    """
    Record or update a symlink in the database.
    
    Args:
        path: The symlink path
        target: The target path (or None if unreadable)
        status: Status string (e.g., 'ok' or 'broken')
    """
    with _db_lock:
        conn = get_connection()
        initialize_schema(conn)
        now = dt.datetime.utcnow().isoformat()
        cur = conn.cursor()
        cur.execute("SELECT path FROM symlinks WHERE path=?", (path,))
        if cur.fetchone():
            cur.execute(
                "UPDATE symlinks SET last_target=?, status=?, last_status=?, last_seen_utc=? WHERE path=?",
                (target, status, status, now, path)
            )
        else:
            cur.execute(
                "INSERT INTO symlinks(path, last_target, status, last_status, first_seen_utc, last_seen_utc) VALUES(?,?,?,?,?,?)",
                (path, target, status, status, now, now)
            )
        conn.commit()
        conn.close()


def enqueue_action(url: str, reason: str = "", related_path: str | None = None):
    """
    Enqueue a repair action (URL to be invoked).
    
    Args:
        url: The URL to invoke for repair/search
        reason: Reason for the action (e.g., 'auto-search')
        related_path: The symlink path related to this action
    """
    with _db_lock:
        conn = get_connection()
        initialize_schema(conn)
        cur = conn.cursor()
        # De-dupe on url if still pending
        cur.execute("SELECT id FROM actions WHERE url=? AND status='pending'", (url,))
        if cur.fetchone():
            conn.close()
            return
        cur.execute(
            "INSERT INTO actions(url, reason, related_path, created_utc, status) VALUES(?,?,?,?,?)",
            (url, reason, related_path, dt.datetime.utcnow().isoformat(), 'pending')
        )
        conn.commit()
        conn.close()


def get_pending_actions(limit: int = 25):
    """
    Get pending actions from the queue.
    
    Args:
        limit: Maximum number of actions to return
        
    Returns:
        List of Row objects with id and url fields
    """
    with _db_lock:
        conn = get_connection()
        initialize_schema(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, url FROM actions WHERE status='pending' ORDER BY id ASC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return rows


def mark_action_sent(action_id: int, ok: bool):
    """
    Mark an action as sent or failed.
    
    Args:
        action_id: The action ID
        ok: True if sent successfully, False if failed
    """
    with _db_lock:
        conn = get_connection()
        initialize_schema(conn)
        cur = conn.cursor()
        cur.execute(
            "UPDATE actions SET status=?, fired_utc=? WHERE id=?",
            ("sent" if ok else "failed", dt.datetime.utcnow().isoformat(), action_id)
        )
        conn.commit()
        conn.close()


def update_symlink_status(path: str, status: str):
    """
    Update the status of a symlink.
    
    Args:
        path: The symlink path
        status: New status string
    """
    with _db_lock:
        conn = get_connection()
        initialize_schema(conn)
        cur = conn.cursor()
        cur.execute(
            "UPDATE symlinks SET status=?, last_status=? WHERE path=?",
            (status, status, path)
        )
        conn.commit()
        conn.close()


def lookup_symlink(conn: sqlite3.Connection, original_path: str) -> Optional[str]:
    """
    Look up the symlink path for an original file path.
    
    Args:
        conn: Database connection
        original_path: The original file path (target)
        
    Returns:
        The symlink path if found, None otherwise
    """
    try:
        cur = conn.execute("SELECT path FROM symlinks WHERE last_target = ? LIMIT 1", (original_path,))
        row = cur.fetchone()
        return row["path"] if row else None
    except sqlite3.Error:
        return None


def upsert(conn: sqlite3.Connection, table: str, keys: dict, update: dict):
    """
    Upsert helper compatible with a wide range of SQLite versions.
    
    If 'id' is present in keys, attempts to UPDATE the row first;
    if no row was updated, INSERTs the combined data.
    Otherwise falls back to INSERT OR REPLACE.
    
    Args:
        conn: Database connection
        table: Table name
        keys: Key columns (used for matching existing rows)
        update: Columns to update/insert
    """
    cols = list({*keys.keys(), *update.keys()})
    data = {**keys, **update}
    
    if "id" in keys:
        # Try to do a plain UPDATE first
        setters = ", ".join([f"{c}=:{c}" for c in update.keys()])
        update_sql = f"UPDATE {table} SET {setters} WHERE id=:id;"
        cur = conn.execute(update_sql, data)
        # If no rows updated, do an INSERT
        if cur.rowcount == 0:
            placeholders = ", ".join([f":{c}" for c in cols])
            insert_sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders});"
            conn.execute(insert_sql, data)
    else:
        # Fallback: replace whole row when no id key provided
        placeholders = ", ".join([f":{c}" for c in cols])
        sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders});"
        conn.execute(sql, data)


def add_events(rows: list[tuple[int, str, str | None, str | None, str | None, str | None, str | None]]):
    """
    Add multiple event records to the events table.
    
    Args:
        rows: List of tuples (ts, path, target, kind, name, action, status)
              - ts: Unix timestamp (integer)
              - path: Symlink path (string)
              - target: Target path or None (string or None)
              - kind: Media type (string or None)
              - name: Show/movie name (string or None)
              - action: Action taken (string or None)
              - status: Event status (string or None)
    """
    conn = get_connection()
    initialize_schema(conn)
    conn.executemany(
        "INSERT INTO events (ts, path, target, kind, name, action, status) VALUES (?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    conn.close()
