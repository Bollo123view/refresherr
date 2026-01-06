from __future__ import annotations

import os
import re
import time
import json
import sqlite3
import pathlib
import logging
from typing import Optional, Tuple, Dict, Any

import requests

# -----------------------------
# Env / Config
# -----------------------------
DB_PATH = os.environ.get("DB_PATH", "/data/symlinks.db")

# Roots to scan (comma-separated)
SYMLINK_ROOTS = [x.strip() for x in os.environ.get("SYMLINK_ROOTS", "/opt/media/jelly").split(",") if x.strip()]

# Ignore if substring appears anywhere in path (comma-separated)
IGNORE_SUBSTR = [x.strip() for x in os.environ.get("IGNORE_SUBSTR", "cinesync").split(",") if x.strip()]

# How often to commit batches
COMMIT_EVERY = int(os.environ.get("COMMIT_EVERY", "1000"))

# Optional probes: comma-separated absolute paths. We record whether they exist at scan time.
PROBE_PATHS = [x.strip() for x in os.environ.get("PROBE_PATHS", "").split(",") if x.strip()]

# Optional Zurg health probe (if you expose something; if not, leave blank)
ZURG_HEALTH_URL = os.environ.get("ZURG_HEALTH_URL", "").strip()
ZURG_TIMEOUT = float(os.environ.get("ZURG_TIMEOUT", "2.5"))

# SQLite contention tuning
SQLITE_TIMEOUT_SEC = float(os.environ.get("SQLITE_TIMEOUT_SEC", "60"))
SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get("SQLITE_BUSY_TIMEOUT_MS", "60000"))
SQLITE_WRITE_RETRIES = int(os.environ.get("SQLITE_WRITE_RETRIES", "10"))
SQLITE_RETRY_BASE_SLEEP = float(os.environ.get("SQLITE_RETRY_BASE_SLEEP", "0.10"))
SQLITE_RETRY_MAX_SLEEP = float(os.environ.get("SQLITE_RETRY_MAX_SLEEP", "2.0"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# -----------------------------
# Metadata parsing helpers
# -----------------------------
SXXE_RE = re.compile(r"\bS(?P<s>\d{1,2})E(?P<e>\d{1,3})\b", re.IGNORECASE)
X_RE = re.compile(r"\b(?P<s>\d{1,2})x(?P<e>\d{2,3})\b", re.IGNORECASE)
SEASON_DIR_RE = re.compile(r"^Season\s+(?P<n>\d+)$", re.IGNORECASE)


def _now() -> int:
    return int(time.time())


def _ms() -> int:
    return int(time.time() * 1000)


def extract_meta_from_path(p: pathlib.Path) -> Dict[str, Any]:
    """
    Best-effort extraction for dashboard grouping.
    """
    parts = list(p.parts)
    meta: Dict[str, Any] = {
        "library": None,
        "show": None,
        "season": None,
        "episode": None,
        "ext": p.suffix.lower().lstrip(".") if p.suffix else None,
        "filename": p.name,
        "parent_dir": str(p.parent),
    }

    # Try to locate /opt/media/jelly/<library>/...
    try:
        jelly_idx = parts.index("jelly")
        if jelly_idx + 1 < len(parts):
            meta["library"] = parts[jelly_idx + 1]
            if jelly_idx + 2 < len(parts):
                meta["show"] = parts[jelly_idx + 2]
            if jelly_idx + 3 < len(parts):
                m = SEASON_DIR_RE.match(parts[jelly_idx + 3])
                if m:
                    meta["season"] = int(m.group("n"))
    except ValueError:
        pass

    m = SXXE_RE.search(p.name)
    if m:
        meta["season"] = meta["season"] or int(m.group("s"))
        meta["episode"] = int(m.group("e"))
    else:
        m2 = X_RE.search(p.name)
        if m2:
            meta["season"] = meta["season"] or int(m2.group("s"))
            meta["episode"] = int(m2.group("e"))

    return meta


# -----------------------------
# SQLite helpers (heavy-write safe)
# -----------------------------
def _is_locked_err(e: Exception) -> bool:
    msg = str(e).lower()
    return "database is locked" in msg or "database table is locked" in msg or "busy" in msg


def _exec_retry(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    *,
    retries: int | None = None,
) -> sqlite3.Cursor:
    """
    Execute a statement with retries when SQLite is busy/locked.
    Intended for writes and schema ops.
    """
    retries = SQLITE_WRITE_RETRIES if retries is None else retries
    delay = SQLITE_RETRY_BASE_SLEEP
    last_exc: Optional[Exception] = None

    for attempt in range(retries):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            last_exc = e
            if not _is_locked_err(e) or attempt == retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, SQLITE_RETRY_MAX_SLEEP)

    # Unreachable, but keeps type-checkers happy
    if last_exc:
        raise last_exc
    return conn.execute(sql, params)


def _commit_retry(conn: sqlite3.Connection, *, retries: int | None = None) -> None:
    retries = SQLITE_WRITE_RETRIES if retries is None else retries
    delay = SQLITE_RETRY_BASE_SLEEP
    last_exc: Optional[Exception] = None

    for attempt in range(retries):
        try:
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            last_exc = e
            if not _is_locked_err(e) or attempt == retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, SQLITE_RETRY_MAX_SLEEP)

    if last_exc:
        raise last_exc


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SEC)
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")
    return conn


# -----------------------------
# DB schema helpers
# -----------------------------
def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_col(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    if col not in _table_cols(conn, table):
        _exec_retry(conn, f"ALTER TABLE {table} ADD COLUMN {ddl}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    _exec_retry(conn, """
        CREATE TABLE IF NOT EXISTS scans (
            scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_utc INTEGER NOT NULL,
            finished_utc INTEGER,
            duration_ms INTEGER,
            roots_json TEXT,
            probe_json TEXT,
            zurg_json TEXT,
            total_symlinks INTEGER DEFAULT 0,
            ok_count INTEGER DEFAULT 0,
            broken_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0
        )
    """)

    _exec_retry(conn, """
        CREATE TABLE IF NOT EXISTS symlinks (
            path TEXT PRIMARY KEY,

            last_target TEXT,
            last_status TEXT,
            last_error TEXT,

            library TEXT,
            show TEXT,
            season INTEGER,
            episode INTEGER,
            ext TEXT,
            filename TEXT,
            parent_dir TEXT,

            first_seen_utc INTEGER,
            last_seen_utc INTEGER,
            last_checked_utc INTEGER,
            status_changed_utc INTEGER,

            first_broken_utc INTEGER,
            last_broken_utc INTEGER,
            last_ok_utc INTEGER,

            seen_count INTEGER DEFAULT 0,
            broken_count INTEGER DEFAULT 0,
            ok_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,

            last_scan_id INTEGER,
            broken_age_seconds INTEGER DEFAULT 0
        )
    """)

    _exec_retry(conn, """
        CREATE TABLE IF NOT EXISTS symlink_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utc INTEGER NOT NULL,
            path TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT,
            scan_id INTEGER,
            note TEXT
        )
    """)

    _exec_retry(conn, """
        CREATE TABLE IF NOT EXISTS quarantines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            original_path TEXT NOT NULL,
            quarantine_path TEXT NOT NULL,

            library TEXT,
            show TEXT,
            season INTEGER,
            episode INTEGER,
            filename TEXT,
            ext TEXT,
            parent_dir TEXT,

            created_utc INTEGER NOT NULL,
            created_scan_id INTEGER,

            last_seen_in_quarantine_utc INTEGER,
            last_note TEXT,

            state TEXT NOT NULL DEFAULT 'quarantined',
            resolved_utc INTEGER,
            resolved_scan_id INTEGER,
            resolve_reason TEXT
        )
    """)

    # Indexes
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_symlinks_status ON symlinks(last_status)")
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_symlinks_show_season ON symlinks(show, season)")
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_symlinks_first_broken ON symlinks(first_broken_utc)")
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_symlinks_last_broken ON symlinks(last_broken_utc)")
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_symlinks_last_seen ON symlinks(last_seen_utc)")

    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_quar_state ON quarantines(state)")
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_quar_show_season ON quarantines(show, season)")
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_quar_created ON quarantines(created_utc)")
    _exec_retry(conn, "CREATE INDEX IF NOT EXISTS idx_quar_original ON quarantines(original_path)")

    # Convenience columns on symlinks (safe groundwork)
    _ensure_col(conn, "symlinks", "quarantine_state", "quarantine_state TEXT")
    _ensure_col(conn, "symlinks", "quarantine_last_seen_utc", "quarantine_last_seen_utc INTEGER")

    _commit_retry(conn)


# -----------------------------
# Scanning logic
# -----------------------------
def is_ignored(path: pathlib.Path) -> bool:
    s = str(path)
    return any(x and x in s for x in IGNORE_SUBSTR)


def check_symlink(path: pathlib.Path) -> Tuple[str, Optional[str], Optional[str]]:
    if not path.is_symlink():
        return "skip", None, None

    try:
        target = os.readlink(path)
        if not os.path.isabs(target):
            target = os.path.abspath(os.path.join(path.parent, target))

        if os.path.exists(target):
            return "ok", target, None
        return "broken", target, None
    except OSError as e:
        return "error", None, str(e)


def _resolve_quarantine_if_replaced(conn: sqlite3.Connection, original_path: str, scan_id: int, now: int) -> None:
    row = conn.execute(
        """
        SELECT id FROM quarantines
        WHERE original_path=? AND state='quarantined'
        ORDER BY created_utc DESC
        LIMIT 1
        """,
        (original_path,),
    ).fetchone()

    if not row:
        return

    qid = int(row[0])

    _exec_retry(conn, """
        UPDATE quarantines
        SET state='resolved',
            resolved_utc=?,
            resolved_scan_id=?,
            resolve_reason='replacement_seen'
        WHERE id=?
    """, (now, scan_id, qid))

    _exec_retry(conn, """
        UPDATE symlinks
        SET quarantine_state=NULL,
            quarantine_last_seen_utc=NULL
        WHERE path=?
    """, (original_path,))


def record_observation(
    conn: sqlite3.Connection,
    scan_id: int,
    path: str,
    target: Optional[str],
    status: str,
    error: Optional[str],
    meta: Dict[str, Any],
    now: int,
) -> None:
    cur = conn.execute(
        "SELECT last_status, first_seen_utc, first_broken_utc, broken_count, ok_count, error_count, seen_count FROM symlinks WHERE path=?",
        (path,),
    )
    row = cur.fetchone()

    old_status = None
    first_seen = None
    first_broken = None
    broken_count = ok_count = error_count = seen_count = 0

    if row:
        old_status, first_seen, first_broken, broken_count, ok_count, error_count, seen_count = row

    is_new = row is None
    status_changed = (old_status != status) if not is_new else True

    seen_count = (seen_count or 0) + 1
    if status == "broken":
        broken_count = (broken_count or 0) + 1
    elif status == "ok":
        ok_count = (ok_count or 0) + 1
    elif status == "error":
        error_count = (error_count or 0) + 1

    first_seen_utc = first_seen or now
    last_seen_utc = now
    last_checked_utc = now
    status_changed_utc = now if status_changed else None

    first_broken_utc = first_broken
    last_broken_utc = None
    last_ok_utc = None

    if status == "broken":
        if first_broken_utc is None:
            first_broken_utc = now
        last_broken_utc = now
    if status == "ok":
        last_ok_utc = now

    broken_age_seconds = 0
    if status == "broken" and first_broken_utc:
        broken_age_seconds = max(0, now - first_broken_utc)

    _exec_retry(conn, """
        INSERT INTO symlinks (
            path, last_target, last_status, last_error,
            library, show, season, episode, ext, filename, parent_dir,
            first_seen_utc, last_seen_utc, last_checked_utc, status_changed_utc,
            first_broken_utc, last_broken_utc, last_ok_utc,
            seen_count, broken_count, ok_count, error_count,
            last_scan_id, broken_age_seconds,
            quarantine_state, quarantine_last_seen_utc
        )
        VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            NULL, NULL
        )
        ON CONFLICT(path) DO UPDATE SET
            last_target=excluded.last_target,
            last_status=excluded.last_status,
            last_error=excluded.last_error,

            library=COALESCE(excluded.library, symlinks.library),
            show=COALESCE(excluded.show, symlinks.show),
            season=COALESCE(excluded.season, symlinks.season),
            episode=COALESCE(excluded.episode, symlinks.episode),
            ext=COALESCE(excluded.ext, symlinks.ext),
            filename=COALESCE(excluded.filename, symlinks.filename),
            parent_dir=COALESCE(excluded.parent_dir, symlinks.parent_dir),

            first_seen_utc=symlinks.first_seen_utc,
            last_seen_utc=excluded.last_seen_utc,
            last_checked_utc=excluded.last_checked_utc,
            status_changed_utc=COALESCE(excluded.status_changed_utc, symlinks.status_changed_utc),

            first_broken_utc=COALESCE(symlinks.first_broken_utc, excluded.first_broken_utc),
            last_broken_utc=COALESCE(excluded.last_broken_utc, symlinks.last_broken_utc),
            last_ok_utc=COALESCE(excluded.last_ok_utc, symlinks.last_ok_utc),

            seen_count=?,
            broken_count=?,
            ok_count=?,
            error_count=?,

            last_scan_id=?,
            broken_age_seconds=excluded.broken_age_seconds
    """, (
        path, target, status, error,
        meta.get("library"), meta.get("show"), meta.get("season"), meta.get("episode"),
        meta.get("ext"), meta.get("filename"), meta.get("parent_dir"),
        first_seen_utc, last_seen_utc, last_checked_utc, status_changed_utc,
        first_broken_utc, last_broken_utc, last_ok_utc,
        seen_count, broken_count, ok_count, error_count,
        scan_id, broken_age_seconds,
        # update counters + scan id
        seen_count, broken_count, ok_count, error_count,
        scan_id
    ))

    if status_changed and not is_new:
        _exec_retry(
            conn,
            "INSERT INTO symlink_events (utc, path, old_status, new_status, scan_id, note) VALUES (?, ?, ?, ?, ?, ?)",
            (now, path, old_status, status, scan_id, None),
        )

    if status == "ok":
        _resolve_quarantine_if_replaced(conn, path, scan_id, now)


def create_scan_row(conn: sqlite3.Connection, roots: list[str]) -> int:
    started = _now()
    probe = {p: os.path.exists(p) for p in PROBE_PATHS} if PROBE_PATHS else {}
    zurg_info: Dict[str, Any] = {}

    if ZURG_HEALTH_URL:
        try:
            t0 = _ms()
            r = requests.get(ZURG_HEALTH_URL, timeout=ZURG_TIMEOUT)
            zurg_info = {"url": ZURG_HEALTH_URL, "status": r.status_code, "latency_ms": (_ms() - t0)}
        except Exception as e:
            zurg_info = {"url": ZURG_HEALTH_URL, "error": str(e)}

    cur = _exec_retry(
        conn,
        "INSERT INTO scans (started_utc, roots_json, probe_json, zurg_json) VALUES (?, ?, ?, ?)",
        (started, json.dumps(roots), json.dumps(probe), json.dumps(zurg_info)),
    )
    _commit_retry(conn)
    return int(cur.lastrowid)


def finalize_scan_row(
    conn: sqlite3.Connection,
    scan_id: int,
    started_utc: int,
    total_symlinks: int,
    ok_count: int,
    broken_count: int,
    error_count: int,
) -> None:
    finished = _now()
    duration_ms = int((finished - started_utc) * 1000)

    _exec_retry(conn, """
        UPDATE scans
        SET finished_utc=?, duration_ms=?, total_symlinks=?, ok_count=?, broken_count=?, error_count=?
        WHERE scan_id=?
    """, (finished, duration_ms, total_symlinks, ok_count, broken_count, error_count, scan_id))

    _commit_retry(conn)


def scan_once() -> None:
    logging.info("Starting manual-mode scan")
    now = _now()

    conn = _connect()
    ensure_schema(conn)

    scan_id = create_scan_row(conn, SYMLINK_ROOTS)
    started_utc = conn.execute("SELECT started_utc FROM scans WHERE scan_id=?", (scan_id,)).fetchone()[0]

    total_symlinks = 0
    ok_count = 0
    broken_count = 0
    error_count = 0

    ops_since_commit = 0

    try:
        for root in SYMLINK_ROOTS:
            base = pathlib.Path(root)
            if not base.exists():
                logging.warning("Root missing: %s", root)
                continue

            for item in base.rglob("*"):
                if is_ignored(item):
                    continue

                status, target, err = check_symlink(item)
                if status == "skip":
                    continue

                total_symlinks += 1
                if status == "ok":
                    ok_count += 1
                elif status == "broken":
                    broken_count += 1
                elif status == "error":
                    error_count += 1

                meta = extract_meta_from_path(item)
                record_observation(
                    conn=conn,
                    scan_id=scan_id,
                    path=str(item),
                    target=target,
                    status=status,
                    error=err,
                    meta=meta,
                    now=now,
                )

                ops_since_commit += 1
                if ops_since_commit >= COMMIT_EVERY:
                    _commit_retry(conn)
                    ops_since_commit = 0

        # Final commit for remainder
        if ops_since_commit:
            _commit_retry(conn)

        finalize_scan_row(conn, scan_id, started_utc, total_symlinks, ok_count, broken_count, error_count)

    finally:
        conn.close()

    logging.info(
        "Scan complete (manual mode, no actions enqueued). total=%d ok=%d broken=%d error=%d",
        total_symlinks, ok_count, broken_count, error_count
    )


def run_loop(*args, **kwargs) -> None:
    interval = int(os.environ.get("SCAN_INTERVAL", "900"))
    once = os.environ.get("SCAN_ONCE", "0") == "1"

    while True:
        try:
            scan_once()
        except Exception as e:
            logging.exception("Scanner loop error: %s", e)

        if once:
            return

        time.sleep(interval)


if __name__ == "__main__":
    run_loop()

