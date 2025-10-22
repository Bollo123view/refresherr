from __future__ import annotations
import os, sqlite3, datetime as dt, urllib.parse, threading

DEFAULT_DB = os.path.join(os.environ.get("DATA_DIR","/data"), "symlinks.db")
_db_lock = threading.Lock()

def url_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")

def _conn():
    os.makedirs(os.path.dirname(DEFAULT_DB), exist_ok=True)
    conn = sqlite3.connect(DEFAULT_DB)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def _migrate(conn):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS symlinks(
        path TEXT PRIMARY KEY,
        last_target TEXT,
        status TEXT,
        first_seen_utc TEXT,
        last_seen_utc TEXT
    );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS actions(
        id INTEGER PRIMARY KEY,
        url TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', -- pending|sent|failed
        reason TEXT,
        related_path TEXT,
        created_utc TEXT,
        fired_utc TEXT
    );""")
    conn.commit()

def record_symlink(path: str, target: str|None, status: str):
    with _db_lock:
        conn = _conn(); _migrate(conn)
        now = dt.datetime.utcnow().isoformat()
        cur = conn.cursor()
        cur.execute("SELECT path FROM symlinks WHERE path=?", (path,))
        if cur.fetchone():
            cur.execute("UPDATE symlinks SET last_target=?, status=?, last_seen_utc=? WHERE path=?",
                        (target, status, now, path))
        else:
            cur.execute("INSERT INTO symlinks(path,last_target,status,first_seen_utc,last_seen_utc) VALUES(?,?,?,?,?)",
                        (path, target, status, now, now))
        conn.commit(); conn.close()

def enqueue_action(url: str, reason: str="", related_path: str|None=None):
    with _db_lock:
        conn = _conn(); _migrate(conn)
        cur = conn.cursor()
        # de-dupe on url if still pending
        cur.execute("SELECT id FROM actions WHERE url=? AND status='pending'", (url,))
        if cur.fetchone():
            conn.close(); return
        cur.execute("INSERT OR IGNORE INTO actions(url, reason, related_path, created_utc) VALUES(?,?,?,strftime('%s','now'))",
                    (url, reason, related_path, dt.datetime.utcnow().isoformat()))
        conn.commit(); conn.close()

def get_pending(limit: int=25):
    with _db_lock:
        conn = _conn(); _migrate(conn)
        cur = conn.cursor()
        cur.execute("SELECT id, url FROM actions WHERE status='pending' ORDER BY id ASC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        return rows

def mark_sent(action_id: int, ok: bool):
    with _db_lock:
        conn = _conn(); _migrate(conn)
        cur = conn.cursor()
        cur.execute("UPDATE actions SET status=?, fired_utc=? WHERE id=?",
                    ("sent" if ok else "failed", dt.datetime.utcnow().isoformat(), action_id))
        conn.commit(); conn.close()

def update_symlink_status(path: str, status: str):
    with _db_lock:
        conn = _conn(); _migrate(conn)
        cur = conn.cursor()
        # Try last_status first, fall back to status for older schema
        try:
            cur.execute("UPDATE symlinks SET last_status=? WHERE path=?", (status, path))
            if cur.rowcount == 0:
                cur.execute("UPDATE symlinks SET status=? WHERE path=?", (status, path))
        except Exception:
            cur.execute("UPDATE symlinks SET status=? WHERE path=?", (status, path))
        conn.commit(); conn.close()
