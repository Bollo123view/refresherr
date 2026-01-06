"""CineSync repair tool - uses central DB module."""
from __future__ import annotations

import os
import re
import time
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Tuple, Iterable
from app.refresher.core import db

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# -----------------------------
# Env
# -----------------------------
DB_PATH = os.environ.get("DB_PATH", "/data/symlinks.db")

# CineSync base (your layout)
CINESYNC_BASE = Path(os.environ.get("CINESYNC_BASE", "/opt/media/jelly/cinesync/CineSync"))

# Where your "live" symlinks live (we will repair broken links here)
REPAIR_ROOTS = [
    x.strip()
    for x in os.environ.get("CINESYNC_REPAIR_ROOTS", "/opt/media/jelly/tv,/opt/media/jelly/hayu").split(",")
    if x.strip()
]

# Safety switches
DRY_RUN = os.environ.get("CINESYNC_DRY_RUN", "1") == "1"
LIMIT = int(os.environ.get("CINESYNC_LIMIT", "200"))  # max broken symlinks to attempt per run

# IMPORTANT: we will ONLY create symlinks to resolved targets under these prefixes
ALLOWED_TARGET_PREFIXES = [
    x.strip()
    for x in os.environ.get("CINESYNC_ALLOWED_TARGET_PREFIXES", "/mnt/remote").split(",")
    if x.strip()
]

# default: no rewrite (keep /mnt/.. targets)
PATH_REWRITE_MAP_RAW = os.environ.get("CINESYNC_PATH_REWRITE_MAP", "").strip()

# Prefer higher resolution if multiple candidates exist
def resolution_rank(name: str) -> int:
    n = (name or "").lower()
    if "2160" in n or "4k" in n:
        return 40
    if "1080" in n:
        return 30
    if "720" in n:
        return 20
    if "480" in n:
        return 10
    return 0


# -----------------------------
# Regex helpers
# -----------------------------
SXXE_RE = re.compile(r"\bS(?P<s>\d{1,2})E(?P<e>\d{1,3})\b", re.IGNORECASE)
X_RE = re.compile(r"\b(?P<s>\d{1,2})x(?P<e>\d{2,3})\b", re.IGNORECASE)
TMDB_RE = re.compile(r"\{tmdb-(\d+)\}", re.IGNORECASE)
YEAR_RE = re.compile(r"\((\d{4})\)")

def norm_title(s: str) -> str:
    s = (s or "").lower().strip()
    s = YEAR_RE.sub("", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_episode_token(name: str) -> Optional[Tuple[int, int]]:
    m = SXXE_RE.search(name or "")
    if m:
        return int(m.group("s")), int(m.group("e"))
    m2 = X_RE.search(name or "")
    if m2:
        return int(m2.group("s")), int(m2.group("e"))
    return None

def parse_tmdb_id(folder_name: str) -> Optional[int]:
    m = TMDB_RE.search(folder_name or "")
    return int(m.group(1)) if m else None

def parse_year(folder_name: str) -> Optional[int]:
    m = YEAR_RE.search(folder_name or "")
    return int(m.group(1)) if m else None

def is_symlink_ok(p: Path) -> bool:
    if not p.is_symlink():
        return False
    try:
        return os.path.exists(str(p))  # follows chain
    except OSError:
        return False

def is_broken_symlink(p: Path) -> bool:
    return p.is_symlink() and not is_symlink_ok(p)


# -----------------------------
# DB helpers (migrations)
# -----------------------------
def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

def _ensure_col(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    cols = _table_cols(conn, table)
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Ensure schema for cinesync-specific tables.
    The central DB module handles the main schema.
    """
    # Initialize main schema first
    db.initialize_schema(conn)
    
    # Busy timeout helps a lot under concurrent writes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=8000;")

    # --- CineSync index table ---
    conn.execute("""
    CREATE TABLE IF NOT EXISTS cinesync_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER,
        show_title TEXT,
        show_norm TEXT,
        year INTEGER,
        season INTEGER,
        episode INTEGER,
        path TEXT UNIQUE,
        target_ok INTEGER DEFAULT 0,
        resolution_rank INTEGER DEFAULT 0,
        first_seen_utc INTEGER,
        last_seen_utc INTEGER
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_tmdb ON cinesync_items(tmdb_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_norm ON cinesync_items(show_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_lookup ON cinesync_items(show_norm, season, episode)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cs_se ON cinesync_items(season, episode)")
    conn.commit()

    # Migrate older cinesync_items tables if needed
    _ensure_col(conn, "cinesync_items", "tmdb_id", "tmdb_id INTEGER")
    _ensure_col(conn, "cinesync_items", "show_title", "show_title TEXT")
    _ensure_col(conn, "cinesync_items", "show_norm", "show_norm TEXT")
    _ensure_col(conn, "cinesync_items", "year", "year INTEGER")
    _ensure_col(conn, "cinesync_items", "season", "season INTEGER")
    _ensure_col(conn, "cinesync_items", "episode", "episode INTEGER")
    _ensure_col(conn, "cinesync_items", "path", "path TEXT")
    _ensure_col(conn, "cinesync_items", "target_ok", "target_ok INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_items", "resolution_rank", "resolution_rank INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_items", "first_seen_utc", "first_seen_utc INTEGER")
    _ensure_col(conn, "cinesync_items", "last_seen_utc", "last_seen_utc INTEGER")
    conn.commit()

    # --- Runs table ---
    conn.execute("""
    CREATE TABLE IF NOT EXISTS cinesync_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_utc INTEGER NOT NULL,
        finished_utc INTEGER,
        dry_run INTEGER NOT NULL,
        repair_roots TEXT,
        cinesync_base TEXT,
        allowed_prefixes TEXT,
        indexed_count INTEGER DEFAULT 0,
        checked_broken INTEGER DEFAULT 0,
        candidate_found INTEGER DEFAULT 0,
        resolved_target_ok INTEGER DEFAULT 0,
        replaced INTEGER DEFAULT 0,
        skipped INTEGER DEFAULT 0,
        errors INTEGER DEFAULT 0
    )
    """)
    conn.commit()

    # Migrate older cinesync_runs tables (this is what you hit)
    _ensure_col(conn, "cinesync_runs", "repair_roots", "repair_roots TEXT")
    _ensure_col(conn, "cinesync_runs", "cinesync_base", "cinesync_base TEXT")
    _ensure_col(conn, "cinesync_runs", "allowed_prefixes", "allowed_prefixes TEXT")
    _ensure_col(conn, "cinesync_runs", "resolved_target_ok", "resolved_target_ok INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_runs", "candidate_found", "candidate_found INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_runs", "checked_broken", "checked_broken INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_runs", "indexed_count", "indexed_count INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_runs", "replaced", "replaced INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_runs", "skipped", "skipped INTEGER DEFAULT 0")
    _ensure_col(conn, "cinesync_runs", "errors", "errors INTEGER DEFAULT 0")
    conn.commit()


# -----------------------------
# CineSync discovery
# -----------------------------
def iter_cinesync_show_roots(base: Path) -> Iterable[Path]:
    for top in ("Shows", "4KShows", "AnimeShows", "Movies", "4KMovies", "AnimeMovies"):
        p = base / top
        if p.exists() and p.is_dir():
            yield p

def _cinesync_item_target_ok(p: Path) -> int:
    try:
        rp = os.path.realpath(str(p))  # follows symlink chain
        return 1 if os.path.exists(rp) else 0
    except Exception:
        return 0

def index_cinesync(conn: sqlite3.Connection) -> int:
    if not CINESYNC_BASE.exists():
        logging.warning("CineSync base not found: %s", CINESYNC_BASE)
        return 0

    now = int(time.time())
    count = 0

    for root in iter_cinesync_show_roots(CINESYNC_BASE):
        for show_dir in root.iterdir():
            if not show_dir.is_dir():
                continue

            tmdb_id = parse_tmdb_id(show_dir.name)
            year = parse_year(show_dir.name)

            title = TMDB_RE.sub("", show_dir.name).strip()
            title = YEAR_RE.sub("", title).strip()
            show_norm = norm_title(title)

            for season_dir in show_dir.iterdir():
                if not season_dir.is_dir():
                    continue
                m = re.match(r"Season\s+(\d+)", season_dir.name, re.IGNORECASE)
                if not m:
                    continue
                season_num = int(m.group(1))

                for f in season_dir.iterdir():
                    if not (f.is_file() or f.is_symlink()):
                        continue

                    tok = parse_episode_token(f.name) or parse_episode_token(f.stem)
                    if not tok:
                        continue

                    _, e = tok
                    ok = _cinesync_item_target_ok(f)
                    rr = resolution_rank(f.name)

                    conn.execute("""
                        INSERT INTO cinesync_items (
                            tmdb_id, show_title, show_norm, year,
                            season, episode, path, target_ok, resolution_rank,
                            first_seen_utc, last_seen_utc
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            target_ok=excluded.target_ok,
                            resolution_rank=excluded.resolution_rank,
                            last_seen_utc=excluded.last_seen_utc
                    """, (
                        tmdb_id, title, show_norm, year,
                        season_num, e, str(f), ok, rr,
                        now, now
                    ))
                    count += 1

    conn.commit()
    return count


# -----------------------------
# Matching + replacement (DIRECT TO REAL FILE)
# -----------------------------
def find_cinesync_match(conn: sqlite3.Connection, show_folder_name: str, season: int, episode: int) -> Optional[str]:
    tmdb_id = parse_tmdb_id(show_folder_name)
    if tmdb_id:
        row = conn.execute("""
            SELECT path FROM cinesync_items
            WHERE tmdb_id=? AND season=? AND episode=? AND target_ok=1
            ORDER BY resolution_rank DESC
            LIMIT 1
        """, (tmdb_id, season, episode)).fetchone()
        return row[0] if row else None

    sn = norm_title(show_folder_name)
    row = conn.execute("""
        SELECT path FROM cinesync_items
        WHERE show_norm=? AND season=? AND episode=? AND target_ok=1
        ORDER BY resolution_rank DESC
        LIMIT 1
    """, (sn, season, episode)).fetchone()
    return row[0] if row else None

def resolve_real_target(cinesync_path: str) -> Optional[str]:
    """
    IMPORTANT: we DO NOT link to the CineSync symlink.
    We dereference it and link directly to the real underlying file.
    """
    try:
        rp = os.path.realpath(cinesync_path)
        if not rp or not os.path.exists(rp):
            return None
        return rp
    except Exception:
        return None

def target_allowed(real_target: str) -> bool:
    rt = real_target.rstrip("/")
    for prefix in ALLOWED_TARGET_PREFIXES:
        px = prefix.rstrip("/")
        if rt == px or rt.startswith(px + "/"):
            return True
    return False

def replace_symlink_to_real_target(broken_path: Path, cinesync_match_path: str) -> bool:
    if not is_broken_symlink(broken_path):
        return False

    real_target = resolve_real_target(cinesync_match_path)
    if not real_target:
        logging.info("SKIP: match found but real target missing: %s (via %s)", broken_path, cinesync_match_path)
        return False

    if not target_allowed(real_target):
        logging.warning("SKIP: resolved target outside allowed prefixes: %s -> %s", broken_path, real_target)
        return False

    if DRY_RUN:
        logging.info("DRY: REPLACE %s -> %s (via %s)", broken_path, real_target, cinesync_match_path)
        return True

    broken_path.unlink(missing_ok=True)
    os.symlink(real_target, str(broken_path))
    logging.info("REPLACED: %s -> %s (via %s)", broken_path, real_target, cinesync_match_path)
    return True

def iter_broken_symlinks(repair_roots: list[str]) -> Iterable[Path]:
    for root in repair_roots:
        base = Path(root)
        if not base.exists():
            logging.warning("Repair root missing: %s", root)
            continue
        for p in base.rglob("*"):
            if p.is_symlink() and is_broken_symlink(p):
                yield p

def extract_show_from_live_path(p: Path) -> Optional[str]:
    # /opt/media/jelly/<lib>/<Show>/Season N/<file>
    try:
        return p.parents[1].name
    except Exception:
        return None


# -----------------------------
# Runner
# -----------------------------
def _maybe_mark_symlink_state(conn: sqlite3.Connection, path: str, *, method: str, ok: bool, now: int) -> None:
    """Best-effort update into symlinks table if it exists (dashboard fields)."""
    try:
        tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='symlinks'").fetchone()
        if not tbl:
            return

        _ensure_col(conn, "symlinks", "repair_state", "repair_state TEXT")
        _ensure_col(conn, "symlinks", "manual_required", "manual_required INTEGER DEFAULT 0")
        _ensure_col(conn, "symlinks", "manual_reason", "manual_reason TEXT")
        _ensure_col(conn, "symlinks", "attempts_cinesync", "attempts_cinesync INTEGER DEFAULT 0")
        _ensure_col(conn, "symlinks", "last_repair_method", "last_repair_method TEXT")
        _ensure_col(conn, "symlinks", "last_repair_utc", "last_repair_utc INTEGER")
        _ensure_col(conn, "symlinks", "next_retry_utc", "next_retry_utc INTEGER")

        conn.execute(
            """
            UPDATE symlinks
            SET
              attempts_cinesync = COALESCE(attempts_cinesync, 0) + 1,
              last_repair_method = ?,
              last_repair_utc = ?,
              repair_state = CASE WHEN ? THEN 'cinesync' ELSE COALESCE(repair_state, 'cinesync') END,
              manual_required = CASE WHEN ? THEN 0 ELSE COALESCE(manual_required,0) END,
              manual_reason = CASE WHEN ? THEN NULL ELSE manual_reason END
            WHERE path = ?
            """,
            (method, now, 1 if ok else 0, 1 if ok else 0, 1 if ok else 0, path),
        )
    except Exception:
        return


def run_repair_for_paths(paths: Iterable[str], *, dry_run: bool | None = None) -> dict:
    """
    Targeted repair: only attempt the exact paths provided.
    Rewrites the broken live symlink to the *real RD/WebDAV target* (not the CineSync symlink),
    so Jellyfin mounts stay unchanged.
    """
    _dry = DRY_RUN if dry_run is None else bool(dry_run)

    conn = db.get_connection(DB_PATH)
    conn.execute("PRAGMA busy_timeout=8000;")
    ensure_schema(conn)

    started = int(time.time())
    run_id = conn.execute(
        """
        INSERT INTO cinesync_runs (started_utc, dry_run, repair_roots, cinesync_base, allowed_prefixes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (started, 1 if _dry else 0, "custom_paths", str(CINESYNC_BASE), ",".join(ALLOWED_TARGET_PREFIXES)),
    ).lastrowid
    conn.commit()

    indexed = index_cinesync(conn)

    checked = candidates = resolved_ok = replaced = skipped = errors = 0
    replaced_paths: list[str] = []
    skipped_paths: list[str] = []
    error_paths: list[str] = []

    now = int(time.time())

    try:
        for p in paths:
            if not p:
                continue
            checked += 1
            live = Path(p)

            if not is_broken_symlink(live):
                skipped += 1
                skipped_paths.append(str(live))
                continue

            candidates += 1

            show_hint = extract_show_from_live_path(live)
            match = find_cinesync_match(live, show_hint=show_hint, conn=conn, indexed=indexed)
            if not match:
                skipped += 1
                skipped_paths.append(str(live))
                continue

            real_target = resolve_real_target(match)
            if not real_target:
                skipped += 1
                skipped_paths.append(str(live))
                continue

            if not target_allowed(real_target):
                skipped += 1
                skipped_paths.append(str(live))
                continue

            if not is_symlink_ok(real_target):
                skipped += 1
                skipped_paths.append(str(live))
                continue

            resolved_ok += 1

            if _dry:
                logging.info("DRY: would replace %s -> %s (via %s)", live, real_target, match)
                continue

            ok = replace_symlink_to_real_target(live, real_target)
            if ok:
                replaced += 1
                replaced_paths.append(str(live))
                _maybe_mark_symlink_state(conn, str(live), method="cinesync", ok=True, now=now)
            else:
                errors += 1
                error_paths.append(str(live))
                _maybe_mark_symlink_state(conn, str(live), method="cinesync", ok=False, now=now)

    finally:
        finished = int(time.time())
        conn.execute(
            "UPDATE cinesync_runs SET finished_utc=?, checked=?, candidates=?, resolved_ok=?, replaced=?, skipped=?, errors=? WHERE id=?",
            (finished, checked, candidates, resolved_ok, replaced, skipped, errors, run_id),
        )
        conn.commit()
        conn.close()

    logging.info(
        "Done. checked=%d candidates=%d resolved_ok=%d replaced=%d skipped=%d errors=%d dry_run=%s",
        checked, candidates, resolved_ok, replaced, skipped, errors, _dry,
    )

    return {
        "run_id": run_id,
        "checked": checked,
        "candidates": candidates,
        "resolved_ok": resolved_ok,
        "replaced": replaced,
        "skipped": skipped,
        "errors": errors,
        "dry_run": _dry,
        "replaced_paths": replaced_paths,
        "skipped_paths": skipped_paths,
        "error_paths": error_paths,
    }


def run_repair() -> int:
    conn = db.get_connection(DB_PATH)
    conn.execute("PRAGMA busy_timeout=8000;")
    ensure_schema(conn)

    started = int(time.time())
    run_id = conn.execute(
        """
        INSERT INTO cinesync_runs (started_utc, dry_run, repair_roots, cinesync_base, allowed_prefixes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (started, 1 if DRY_RUN else 0, ",".join(REPAIR_ROOTS), str(CINESYNC_BASE), ",".join(ALLOWED_TARGET_PREFIXES)),
    ).lastrowid
    conn.commit()

    indexed = index_cinesync(conn)
    logging.info("CineSync indexed items=%d (base=%s)", indexed, CINESYNC_BASE)

    checked = 0
    candidates = 0
    resolved_ok = 0
    replaced = 0
    skipped = 0
    errors = 0

    try:
        for broken in iter_broken_symlinks(REPAIR_ROOTS):
            if checked >= LIMIT:
                break
            checked += 1

            show = extract_show_from_live_path(broken)
            tok = parse_episode_token(broken.name) or parse_episode_token(broken.stem)
            if not show or not tok:
                skipped += 1
                continue

            season, episode = tok
            match = find_cinesync_match(conn, show, season, episode)
            if not match:
                skipped += 1
                continue

            candidates += 1

            rt = resolve_real_target(match)
            if rt and target_allowed(rt):
                resolved_ok += 1

            try:
                did = replace_symlink_to_real_target(broken, match)
                if did and not DRY_RUN:
                    replaced += 1
            except Exception:
                errors += 1
                logging.exception("Failed replacing %s", broken)

    finally:
        finished = int(time.time())
        conn.execute(
            """
            UPDATE cinesync_runs
            SET finished_utc=?,
                indexed_count=?,
                checked_broken=?,
                candidate_found=?,
                resolved_target_ok=?,
                replaced=?,
                skipped=?,
                errors=?
            WHERE run_id=?
            """,
            (finished, indexed, checked, candidates, resolved_ok, replaced, skipped, errors, run_id),
        )
        conn.commit()
        conn.close()

    logging.info(
        "Done. checked=%d candidates=%d resolved_ok=%d replaced=%d skipped=%d errors=%d dry_run=%s",
        checked, candidates, resolved_ok, replaced, skipped, errors, DRY_RUN
    )
    return 0

def main() -> int:
    logging.info(
        "CineSync repair starting (dry_run=%s limit=%d allowed_prefixes=%s)",
        DRY_RUN, LIMIT, ALLOWED_TARGET_PREFIXES
    )
    return run_repair()

if __name__ == "__main__":
    raise SystemExit(main())

