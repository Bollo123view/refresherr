# app/refresher/core/store.py
from __future__ import annotations
import os, sqlite3, time, typing as t
from contextlib import contextmanager

DEFAULT_DB = os.path.join(os.environ.get("DATA_DIR", "/data"), "symlinks.db")

@contextmanager
def get_conn(db_path: str | None = None):
    path = db_path or DEFAULT_DB
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_schema(db_path: str | None = None):
    with get_conn(db_path) as con:
        cur = con.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_ts  INTEGER NOT NULL,
            duration_s  REAL    DEFAULT 0,
            total       INTEGER DEFAULT 0,
            ok          INTEGER DEFAULT 0,
            broken      INTEGER DEFAULT 0,
            repairing   INTEGER DEFAULT 0,
            mount_ok    INTEGER DEFAULT 1
        );

        -- current snapshot
        CREATE TABLE IF NOT EXISTS symlinks (
            path            TEXT PRIMARY KEY,
            ext             TEXT,
            last_target     TEXT,
            last_status     TEXT CHECK(last_status IN ('ok','broken','repairing')),
            last_size_bytes INTEGER,
            last_mtime_ns   INTEGER,
            first_seen_ts   INTEGER,
            last_seen_ts    INTEGER,
            times_seen      INTEGER DEFAULT 0,
            is_current      INTEGER DEFAULT 1
        );

        -- per-scan history
        CREATE TABLE IF NOT EXISTS symlink_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id         INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
            path            TEXT NOT NULL,
            status          TEXT,
            size_bytes      INTEGER,
            mtime_ns        INTEGER,
            seen_ts         INTEGER NOT NULL
        );

        -- temp seen set for finalize
        CREATE TABLE IF NOT EXISTS scan_seen (
            scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
            path    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_symlinks_status     ON symlinks(last_status);
        CREATE INDEX IF NOT EXISTS idx_symlinks_ext        ON symlinks(ext);
        CREATE INDEX IF NOT EXISTS idx_symlinks_current    ON symlinks(is_current);
        CREATE INDEX IF NOT EXISTS idx_hist_scan           ON symlink_history(scan_id);
        CREATE INDEX IF NOT EXISTS idx_seen_scan           ON scan_seen(scan_id);

        -- FTS5 for fast search
        CREATE VIRTUAL TABLE IF NOT EXISTS symlink_fts USING fts5(
            path,              -- full path text
            last_target,       -- resolved target
            ext,               -- extension
            content=''
        );
        """)
        con.commit()

def begin_scan(db_path: str | None = None) -> int:
    with get_conn(db_path) as con:
        cur = con.cursor()
        cur.execute("INSERT INTO scans (started_ts) VALUES (?)", (int(time.time()),))
        return cur.lastrowid

def _fts_upsert(cur: sqlite3.Cursor, path: str, target: str | None, ext: str | None):
    cur.execute("INSERT INTO symlink_fts (rowid, path, last_target, ext) "
                "VALUES ((SELECT rowid FROM symlinks WHERE path=?),?,?,?) "
                "ON CONFLICT(rowid) DO UPDATE SET path=excluded.path,last_target=excluded.last_target,ext=excluded.ext",
                (path, path, target or "", ext or ""))

def add_items(scan_id: int, items: list[dict], db_path: str | None = None):
    """
    items: dicts with keys: path, ext, target, broken(bool), size_bytes, mtime_ns
    Preserves manual 'repairing' if previously set and file still missing.
    """
    now = int(time.time())
    with get_conn(db_path) as con:
        cur = con.cursor()

        # History + seen
        cur.executemany("""
            INSERT INTO symlink_history (scan_id, path, status, size_bytes, mtime_ns, seen_ts)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (scan_id, it["path"],
             "ok" if not it.get("broken") else "broken",
             it.get("size_bytes"), it.get("mtime_ns"), now)
            for it in items
        ])
        cur.executemany("INSERT INTO scan_seen (scan_id, path) VALUES (?, ?)",
                        [(scan_id, it["path"]) for it in items])

        # Upserts with 'repairing' preservation
        for it in items:
            new_status = "ok" if not it.get("broken") else "broken"
            # check existing to preserve 'repairing'
            cur.execute("SELECT last_status FROM symlinks WHERE path=?", (it["path"],))
            row = cur.fetchone()
            if row and row[0] == "repairing" and new_status == "broken":
                effective_status = "repairing"
            else:
                effective_status = new_status

            cur.execute("""
                INSERT INTO symlinks (path, ext, last_target, last_status, last_size_bytes,
                                      last_mtime_ns, first_seen_ts, last_seen_ts, times_seen, is_current)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
                ON CONFLICT(path) DO UPDATE SET
                    ext             = excluded.ext,
                    last_target     = excluded.last_target,
                    last_status     = ?,
                    last_size_bytes = excluded.last_size_bytes,
                    last_mtime_ns   = excluded.last_mtime_ns,
                    last_seen_ts    = excluded.last_seen_ts,
                    times_seen      = symlinks.times_seen + 1,
                    is_current      = 1
            """, (
                it["path"], it.get("ext"), it.get("target"),
                effective_status,
                it.get("size_bytes"), it.get("mtime_ns"),
                now, now,
                effective_status
            ))

            # FTS sync
            _fts_upsert(cur, it["path"], it.get("target"), it.get("ext"))

def finalize_scan(scan_id: int, summary: dict, db_path: str | None = None):
    with get_conn(db_path) as con:
        cur = con.cursor()
        # Mark entries not seen in this scan as not current
        cur.execute("""
            UPDATE symlinks
            SET is_current = 0
            WHERE is_current = 1
              AND path NOT IN (SELECT path FROM scan_seen WHERE scan_id = ?)
        """, (scan_id,))
        # Compute repairing count directly
        repairing = cur.execute(
            "SELECT COUNT(*) FROM symlinks WHERE is_current=1 AND last_status='repairing'"
        ).fetchone()[0]

        cur.execute("""
            UPDATE scans SET duration_s = ?, total = ?, ok = ?, broken = ?, repairing = ?, mount_ok = ?
            WHERE id = ?
        """, (
            float(summary.get("duration_s", 0.0)),
            int(summary.get("scanned", 0)),
            int(summary.get("ok_files", 0)),
            int(summary.get("broken", 0)),
            int(repairing),
            1 if summary.get("mount_ok", True) else 0,
            scan_id
        ))
        # Optional: keep scan_seen small
        cur.execute("DELETE FROM scan_seen WHERE scan_id = ?", (scan_id,))

# ---------- handy read & admin APIs ------------------------------------------

def get_current_stats(db_path: str | None = None) -> dict:
    with get_conn(db_path) as con:
        cur = con.cursor()
        total = cur.execute("SELECT COUNT(*) FROM symlinks WHERE is_current=1").fetchone()[0]
        ok = cur.execute("SELECT COUNT(*) FROM symlinks WHERE is_current=1 AND last_status='ok'").fetchone()[0]
        broken = cur.execute("SELECT COUNT(*) FROM symlinks WHERE is_current=1 AND last_status='broken'").fetchone()[0]
        repairing = cur.execute("SELECT COUNT(*) FROM symlinks WHERE is_current=1 AND last_status='repairing'").fetchone()[0]
        by_ext = dict(cur.execute("""
            SELECT ext, COUNT(*) FROM symlinks WHERE is_current=1 GROUP BY ext ORDER BY COUNT(*) DESC
        """).fetchall())
        return {"total": total, "ok": ok, "broken": broken, "repairing": repairing, "by_ext": by_ext}

def set_status(path: str, status: str, db_path: str | None = None) -> bool:
    """Manually set status to 'ok' | 'broken' | 'repairing'."""
    if status not in ("ok","broken","repairing"):
        raise ValueError("status must be 'ok' | 'broken' | 'repairing'")
    with get_conn(db_path) as con:
        cur = con.cursor()
        cur.execute("UPDATE symlinks SET last_status=? WHERE path=?", (status, path))
        return cur.rowcount > 0

def search_fts(query: str, limit: int = 25, db_path: str | None = None) -> list[dict]:
    """
    FTS5 search over path/target/ext. Query supports simple tokens and quotes.
    """
    with get_conn(db_path) as con:
        cur = con.cursor()
        rows = cur.execute("""
            SELECT s.path, s.last_target, s.ext, s.last_status
            FROM symlink_fts f
            JOIN symlinks s ON s.rowid = f.rowid
            WHERE symlink_fts MATCH ?
            LIMIT ?
        """, (query, int(limit))).fetchall()
        return [{"path": r[0], "target": r[1], "ext": r[2], "status": r[3]} for r in rows]

