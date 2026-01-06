"""Queue repairs tool - uses central DB module."""
from __future__ import annotations

import os, re, time, sqlite3, urllib.parse
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from app.refresher.core import db

DB_PATH = os.environ.get("DB_PATH", "/data/symlinks.db")

RELAY_BASE = os.environ.get("RELAY_BASE", "http://research-relay:5050/find")
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")

ROUTE_MAP = os.environ.get("ROUTE_MAP", "")
DEFAULT_REASON = "manual_queue"

MEDIA_EXTS = {".mkv",".mp4",".avi",".m4v",".ts",".mov",".wmv"}

SEASON_SEARCH_THRESHOLD = int(os.environ.get("SEASON_SEARCH_THRESHOLD", "2"))

SXXEYY_RE = re.compile(r"(S(?P<s>\d{1,2})E(?P<e>\d{1,3}))", re.IGNORECASE)
SEASON_DIR_RE = re.compile(r"^Season\s*(?P<s>\d{1,2})$", re.IGNORECASE)

def parse_route_map(raw: str) -> list[tuple[str,str]]:
    pairs = []
    for part in [p.strip() for p in raw.split(",") if p.strip()]:
        if "=" not in part:
            continue
        root, typ = part.split("=", 1)
        pairs.append((root.rstrip("/"), typ.strip()))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs

def pick_type(path: str, routes: list[tuple[str,str]]) -> Optional[str]:
    for root, typ in routes:
        if path.startswith(root + "/") or path == root:
            return typ
    return None

def extract_sxxeyy(name: str) -> Optional[str]:
    m = SXXEYY_RE.search(name or "")
    if not m:
        m2 = re.search(r"\b(\d{1,2})x(\d{2,3})\b", name or "", re.IGNORECASE)
        if m2:
            s, e = int(m2.group(1)), int(m2.group(2))
            return f"S{s:02d}E{e:02d}"
        return None
    s = int(m.group("s"))
    e = int(m.group("e"))
    return f"S{s:02d}E{e:02d}"

def extract_show_and_season_from_path(path: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Expecting structure .../<Show Name>/Season N/<file>
    Works for your Jellyfin library layout.
    """
    p = Path(path)
    parts = list(p.parts)
    show = None
    season = None

    for i in range(len(parts)-1):
        m = SEASON_DIR_RE.match(parts[i])
        if m:
            season = int(m.group("s"))
            if i-1 >= 0:
                show = parts[i-1]
            break

    return show, season

def build_episode_term(path: str, typ: str) -> str:
    p = Path(path)
    filename = p.name
    stem = p.stem

    show, season = extract_show_and_season_from_path(path)

    token = extract_sxxeyy(filename) or extract_sxxeyy(stem) or extract_sxxeyy(str(p))
    if typ.startswith("sonarr"):
        if show and token:
            return f"{show} {token}"
        if show:
            return show
        return stem

    # radarr
    parent = p.parent.name
    return parent or stem

def build_season_term(show: str, season: int) -> str:
    return f"{show} S{season:02d}"

def action_exists(conn: sqlite3.Connection, related_path: str, url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM actions WHERE related_path=? AND url=? AND status IN ('pending','sent','repairing') LIMIT 1",
        (related_path, url)
    ).fetchone()
    return row is not None

def enqueue(conn: sqlite3.Connection, url: str, related_path: str, reason: str) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT INTO actions (created_utc, url, reason, related_path, status, last_error) VALUES (?, ?, ?, ?, 'pending', NULL)",
        (now, url, reason, related_path),
    )
    conn.commit()

def build_url(typ: str, scope: str, term: str) -> str:
    q = {
        "token": RELAY_TOKEN,
        "type": typ,
        "scope": scope,
        "term": term,
    }
    return RELAY_BASE + "?" + urllib.parse.urlencode(q)

def main() -> None:
    if not RELAY_TOKEN:
        raise SystemExit("RELAY_TOKEN is not set. Set it in env (RELAY_TOKEN=...)")
    routes = parse_route_map(ROUTE_MAP)
    if not routes:
        raise SystemExit("ROUTE_MAP is not set. Example: ROUTE_MAP=\"/opt/media/jelly/tv=sonarr_tv,/opt/media/jelly/doc=radarr_doc\"")

    limit = int(os.environ.get("QUEUE_LIMIT", "25"))
    reason = os.environ.get("QUEUE_REASON", DEFAULT_REASON)

    conn = db.get_connection(DB_PATH)
    db.initialize_schema(conn)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(symlinks)")}
    # Check for either status or last_status column
    status_col = "last_status" if "last_status" in cols else "status"
    if status_col not in cols or "path" not in cols:
        raise SystemExit("symlinks table missing expected columns (path, status)")

    # Pull broken rows
    rows = conn.execute(
        f"SELECT path FROM symlinks WHERE {status_col}='broken' ORDER BY last_seen_utc DESC LIMIT ?",
        (limit,)
    ).fetchall()

    # Group TV candidates by show+season
    tv_groups: Dict[Tuple[str,str,int], List[str]] = {}
    indiv: List[Tuple[str,str,str]] = []  # (type, scope, path) where term built later

    for (path,) in rows:
        typ = pick_type(path, routes)
        if not typ:
            continue

        if typ.startswith("sonarr"):
            show, season = extract_show_and_season_from_path(path)
            if show and season is not None:
                key = (typ, show, season)
                tv_groups.setdefault(key, []).append(path)
            else:
                indiv.append((typ, "auto", path))
        else:
            # radarr stays per-item (movie search)
            indiv.append((typ, "auto", path))

    queued = 0
    skipped = 0

    # Queue grouped TV seasons if threshold met
    for (typ, show, season), paths in tv_groups.items():
        if len(paths) >= SEASON_SEARCH_THRESHOLD:
            term = build_season_term(show, season)
            url = build_url(typ, "season", term)
            related_path = f"{show}::S{season:02d}"  # grouping key for dedupe
            if action_exists(conn, related_path, url):
                skipped += 1
                continue
            enqueue(conn, url, related_path, reason)
            queued += 1
            print(f"QUEUED(SEASON): {typ} :: {term} :: count={len(paths)}")
        else:
            for p in paths:
                indiv.append((typ, "auto", p))

    # Queue remaining individual actions
    for typ, scope, path in indiv:
        term = build_episode_term(path, typ)
        url = build_url(typ, scope, term)
        if action_exists(conn, path, url):
            skipped += 1
            continue
        enqueue(conn, url, path, reason)
        queued += 1
        print(f"QUEUED: {typ} :: {term} :: {path}")

    print(f"\nDone. queued={queued} skipped={skipped} (limit={limit}, season_threshold={SEASON_SEARCH_THRESHOLD})")

if __name__ == "__main__":
    main()

