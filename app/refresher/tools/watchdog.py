from __future__ import annotations

import os
import time
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import requests

from refresher.tools import cinesync_repair

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

DB_PATH = os.environ.get("DB_PATH", "/data/symlinks.db")

# Relay (already in your .env)
RELAY_BASE = os.environ.get("RELAY_BASE", "").rstrip("/")  # e.g. http://research-relay:5050/find
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")

# Sonarr instances (already in your .env)
SONARR_TV_URL = os.environ.get("SONARR_TV_URL", "").rstrip("/")
SONARR_TV_API = os.environ.get("SONARR_TV_API", "")
SONARR_HAYU_URL = os.environ.get("SONARR_HAYU_URL", "").rstrip("/")
SONARR_HAYU_API = os.environ.get("SONARR_HAYU_API", "")

# Quarantine base (fixed default, no new env required)
QUAR_BASE = Path("/opt/media/jelly/.quarantine")

# Safety defaults (zero-config)
RUN_LIMIT = int(os.environ.get("WATCHDOG_LIMIT", "50"))  # optional override
PER_SHOW_LIMIT = int(os.environ.get("WATCHDOG_PER_SHOW_LIMIT", "1"))  # max seasons per show per run
SEASON_THRESHOLD = int(os.environ.get("WATCHDOG_SEASON_THRESHOLD", "2"))  # >=2 missing -> season search
ARR_COOLDOWN_SEC = int(os.environ.get("WATCHDOG_ARR_COOLDOWN_SEC", "21600"))  # 6h
MAX_ARR_ATTEMPTS = int(os.environ.get("WATCHDOG_MAX_ARR_ATTEMPTS", "3"))

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA busy_timeout=8000;")
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def _ensure_cols(conn: sqlite3.Connection) -> None:
    def cols(table: str) -> set[str]:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    def ensure(table: str, col: str, ddl: str) -> None:
        if col not in cols(table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    ensure("symlinks", "repair_state", "repair_state TEXT")
    ensure("symlinks", "manual_required", "manual_required INTEGER DEFAULT 0")
    ensure("symlinks", "manual_reason", "manual_reason TEXT")
    ensure("symlinks", "attempts_cinesync", "attempts_cinesync INTEGER DEFAULT 0")
    ensure("symlinks", "attempts_arr", "attempts_arr INTEGER DEFAULT 0")
    ensure("symlinks", "last_repair_method", "last_repair_method TEXT")
    ensure("symlinks", "last_repair_utc", "last_repair_utc INTEGER")
    ensure("symlinks", "next_retry_utc", "next_retry_utc INTEGER")
    conn.commit()

def select_broken(conn: sqlite3.Connection, now: int) -> List[Dict[str, Any]]:
    _ensure_cols(conn)
    rows = conn.execute(
        """
        SELECT path, library, show, season, episode, broken_age_seconds,
               COALESCE(manual_required,0), COALESCE(attempts_arr,0), COALESCE(next_retry_utc,0)
        FROM symlinks
        WHERE last_status='broken'
          AND COALESCE(manual_required,0)=0
          AND (next_retry_utc IS NULL OR next_retry_utc <= ?)
        ORDER BY broken_age_seconds DESC, last_broken_utc DESC
        LIMIT ?
        """,
        (now, RUN_LIMIT),
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "path": r[0],
            "library": r[1] or "",
            "show": r[2] or "",
            "season": int(r[3]) if r[3] is not None else None,
            "episode": int(r[4]) if r[4] is not None else None,
            "broken_age_seconds": int(r[5]) if r[5] is not None else 0,
            "attempts_arr": int(r[7]) if r[7] is not None else 0,
        })
    return out

def mark_manual(conn: sqlite3.Connection, path: str, reason: str) -> None:
    now = int(time.time())
    conn.execute(
        """
        UPDATE symlinks
        SET manual_required=1, manual_reason=?, repair_state='manual',
            last_repair_method=COALESCE(last_repair_method,'watchdog'),
            last_repair_utc=?
        WHERE path=?
        """,
        (reason, now, path),
    )

def mark_arr_attempt(conn: sqlite3.Connection, paths: List[str], reason: Optional[str] = None) -> None:
    now = int(time.time())
    for p in paths:
        conn.execute(
            """
            UPDATE symlinks
            SET attempts_arr = COALESCE(attempts_arr,0) + 1,
                repair_state='arr',
                last_repair_method='arr',
                last_repair_utc=?,
                next_retry_utc=?,
                manual_reason=COALESCE(manual_reason, ?)
            WHERE path=?
            """,
            (now, now + ARR_COOLDOWN_SEC, reason, p),
        )

def quarantine_broken_symlink(src: Path) -> Optional[Path]:
    dest = Path(str(QUAR_BASE) + str(src))
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.rename(dest)
        return dest
    except Exception as e:
        logging.warning("Failed to quarantine %s: %s", src, e)
        return None

def _sonarr_series_list(url: str, api: str) -> List[Dict[str, Any]]:
    if not url or not api:
        return []
    r = requests.get(url + "/api/v3/series", headers={"X-Api-Key": api}, timeout=25)
    r.raise_for_status()
    return r.json() or []

def _norm(s: str) -> str:
    import re
    s = (s or "").lower().strip()
    s = re.sub(r"\s+\(\d{4}\)$", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def resolve_sonarr_title(show: str, instance: str) -> Optional[str]:
    if instance == "hayu":
        url, api = SONARR_HAYU_URL, SONARR_HAYU_API
    else:
        url, api = SONARR_TV_URL, SONARR_TV_API
    if not url or not api:
        return None

    wanted = _norm(show)
    best = None

    for s in _sonarr_series_list(url, api):
        title = s.get("title", "")
        if _norm(title) == wanted:
            return title
        if wanted and wanted in _norm(title):
            best = best or title

    return best

def relay_trigger(kind: str, scope: str, term: str) -> bool:
    if not RELAY_BASE or not RELAY_TOKEN:
        return False
    try:
        r = requests.get(RELAY_BASE, params={
            "token": RELAY_TOKEN,
            "type": kind,
            "scope": scope,
            "term": term,
        }, timeout=30)
        if r.status_code >= 400:
            logging.warning("Relay failed %s %s %s -> %s %s", kind, scope, term, r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        logging.warning("Relay exception: %s", e)
        return False

def run_watchdog() -> int:
    now = int(time.time())
    with _conn() as conn:
        broken = select_broken(conn, now)

    if not broken:
        logging.info("Watchdog: no broken symlinks eligible.")
        return 0

    # Per-show gating (avoid spamming one show)
    per_show_seasons: Dict[Tuple[str, str, Optional[int]], int] = {}
    candidates: List[Dict[str, Any]] = []
    for b in broken:
        key = (b.get("library",""), b.get("show",""), b.get("season"))
        per_show_seasons[key] = per_show_seasons.get(key, 0) + 1
        if per_show_seasons[key] == 1:
            candidates.append(b)

    paths = [c["path"] for c in candidates]
    logging.info("Watchdog: stage1 cinesync candidates=%d", len(paths))
    cs = cinesync_repair.run_repair_for_paths(paths, dry_run=False)
    replaced_set = set(cs.get("replaced_paths", []))
    remaining = [c for c in candidates if c["path"] not in replaced_set]

    # Stage 2: ARR replacement for remaining
    groups: Dict[Tuple[str, str, Optional[int]], List[Dict[str, Any]]] = {}
    for r in remaining:
        groups.setdefault((r.get("library",""), r.get("show",""), r.get("season")), []).append(r)

    with _conn() as conn:
        _ensure_cols(conn)

        for (lib, show, season), items in groups.items():
            if any(i.get("attempts_arr", 0) >= MAX_ARR_ATTEMPTS for i in items):
                for i in items:
                    mark_manual(conn, i["path"], "max_arr_attempts_reached")
                continue

            moved_paths: List[str] = []
            for i in items:
                p = Path(i["path"])
                try:
                    if p.is_symlink() and not p.exists():
                        dest = quarantine_broken_symlink(p)
                        if dest:
                            moved_paths.append(i["path"])
                except Exception:
                    continue

            if not moved_paths:
                continue

            instance = "hayu" if (lib or "").lower() == "hayu" else "tv"
            title = resolve_sonarr_title(show, instance) or show
            kind = "sonarr_hayu" if instance == "hayu" else "sonarr_tv"

            if season is not None and len(items) >= SEASON_THRESHOLD:
                term = f"{title} S{int(season)}"
                ok = relay_trigger(kind, "season", term)
                if not ok:
                    for p in moved_paths:
                        mark_manual(conn, p, "relay_season_failed")
                else:
                    mark_arr_attempt(conn, moved_paths)
            else:
                ok_all = True
                for i in items:
                    if season is None or i.get("episode") is None:
                        continue
                    term = f"{title} S{int(season)}E{int(i['episode']):02d}"
                    ok_all = ok_all and relay_trigger(kind, "episode", term)

                if not ok_all:
                    for p in moved_paths:
                        mark_manual(conn, p, "relay_episode_failed")
                else:
                    mark_arr_attempt(conn, moved_paths)

        conn.commit()

    logging.info("Watchdog complete. stage1_replaced=%d remaining=%d", len(replaced_set), len(remaining))
    return 0

def main() -> int:
    return run_watchdog()

if __name__ == "__main__":
    raise SystemExit(main())
