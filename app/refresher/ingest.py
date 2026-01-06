from __future__ import annotations
import os, sys, time, json, sqlite3, datetime as dt
from typing import Dict, Any, List, Optional
import requests
from .core import db

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "symlinks.db")

def discover_instances() -> Dict[str, Dict[str, str]]:
    env = os.environ
    inst: Dict[str, Dict[str, str]] = {}
    for k, v in env.items():
        if k.endswith("_URL") and (k.startswith("SONARR_") or k.startswith("RADARR_")):
            base = k[:-4]
            api_key = env.get(base + "_API", "")
            if not api_key or not v:
                continue
            name = base.lower()
            kind = "sonarr" if name.startswith("sonarr_") else "radarr"
            inst[name] = {"base": v.rstrip("/"), "key": api_key, "kind": kind}
    return inst

def db_conn() -> sqlite3.Connection:
    """Get a database connection using the central DB module."""
    return db.get_connection(DB_PATH)

def ensure_schema(conn: sqlite3.Connection):
    """Ensure schema is initialized using the central DB module."""
    # The central db module handles schema initialization
    db.initialize_schema(conn)

def U(base: str, path: str) -> str:
    return f"{base}/api/v3/{path.lstrip('/') }"

def get_json(method: str, url: str, key: str, **params):
    headers = {"X-Api-Key": key}
    backoff = 1.0
    for attempt in range(6):
        try:
            r = requests.request(method, url, headers=headers, params=params or None, timeout=30)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(backoff); backoff = min(backoff*2, 20)
                continue
            r.raise_for_status()
            if r.headers.get("content-type","" ).startswith("application/json"):
                return r.json()
            return None
        except Exception as e:
            if attempt == 5:
                raise
            time.sleep(backoff); backoff = min(backoff*2, 20)

def upsert(conn: sqlite3.Connection, table: str, keys: Dict[str, Any], update: Dict[str, Any]):
    """
    Upsert helper - now delegates to central DB module.
    """
    db.upsert(conn, table, keys, update)

def lookup_symlink(conn: sqlite3.Connection, original_path: str) -> Optional[str]:
    """
    Look up symlink path - now delegates to central DB module.
    """
    return db.lookup_symlink(conn, original_path)

def ingest_radarr(conn: sqlite3.Connection, name: str, base: str, key: str):
    print(f"[radarr] listing movies from {name} …", flush=True)
    movies = get_json("GET", U(base, "movie"), key) or []
    print(f"[radarr] {name}: {len(movies)} movies", flush=True)
    count_files = 0
    for m in movies:
        keys = {"id": m["id"], "instance": name, "radarr_id": m["id"]}
        upd = {
            "title": m.get("title"),
            "year": m.get("year"),
            "imdb_id": m.get("imdbId"),
            "tmdb_id": m.get("tmdbId"),
            "monitored": 1 if m.get("monitored") else 0,
            "added_utc": m.get("added"),
            "poster_url": f"{base}/MediaCover/{m['id']}/poster.jpg",
            "fanart_url": f"{base}/MediaCover/{m['id']}/fanart.jpg",
        }
        upsert(conn, "movies", keys, upd)

        # per-movie files
        try:
            files = get_json("GET", U(base, "moviefile"), key, movieId=m["id"]) or []
        except Exception as e:
            print(f"[radarr] {name} movie {m['id']}: moviefile?movieId=… failed: {e}", flush=True)
            files = []
        for mf in files:
            count_files += 1
            og = mf.get("path")
            symlink = lookup_symlink(conn, og) if og else None
            keys_f = {"id": mf["id"], "instance": name}
            upd_f = {
                "radarr_movie_id": m["id"],
                "radarr_file_id": mf["id"],
                "quality": ((mf.get("quality") or {}).get("quality") or {}).get("name"),
                "resolution": ((mf.get("quality") or {}).get("quality") or {}).get("resolution"),
                "video_codec": (mf.get("mediaInfo") or {}).get("videoCodec"),
                "audio_codec": (mf.get("mediaInfo") or {}).get("audioFormat"),
                "size_bytes": mf.get("size"),
                "original_path": og,
                "symlink_path": symlink,
            }
            upsert(conn, "movie_files", keys_f, upd_f)
    print(f"[radarr] {name}: wrote {len(movies)} movies, {count_files} files", flush=True)

def ingest_sonarr(conn: sqlite3.Connection, name: str, base: str, key: str):
    print(f"[sonarr] listing series from {name} …", flush=True)
    series = get_json("GET", U(base, "series"), key) or []
    print(f"[sonarr] {name}: {len(series)} series", flush=True)
    count_files = 0
    for s in series:
        sid = s["id"]
        keys = {"id": sid, "instance": name, "sonarr_id": sid}
        upd = {
            "title": s.get("title"),
            "imdb_id": s.get("imdbId"),
            "tvdb_id": s.get("tvdbId"),
            "tmdb_id": s.get("tmdbId"),
            "monitored": 1 if s.get("monitored") else 0,
            "poster_url": f"{base}/MediaCover/{sid}/poster.jpg",
            "fanart_url": f"{base}/MediaCover/{sid}/fanart.jpg",
        }
        upsert(conn, "series", keys, upd)

        # per-series episode files
        try:
            files = get_json("GET", U(base, "episodefile"), key, seriesId=sid) or []
        except Exception as e:
            print(f"[sonarr] {name} series {sid}: episodefile?seriesId=… failed: {e}", flush=True)
            files = []
        for ef in files:
            count_files += 1
            og = ef.get("path")
            symlink = lookup_symlink(conn, og) if og else None
            q = ef.get("quality") or {}
            keys_f = {"id": ef["id"], "instance": name}
            upd_f = {
                "sonarr_series_id": sid,
                "sonarr_file_id": ef["id"],
                "season_number": ef.get("seasonNumber"),
                "quality": (q.get("quality") or {}).get("name"),
                "resolution": (q.get("quality") or {}).get("resolution"),
                "release_group": ef.get("releaseGroup"),
                "size_bytes": ef.get("size"),
                "original_path": og,
                "symlink_path": symlink,
            }
            upsert(conn, "episode_files", keys_f, upd_f)
    print(f"[sonarr] {name}: wrote {len(series)} series, {count_files} files", flush=True)

def main():
    inst = discover_instances()
    if not inst:
        print("No Sonarr/Radarr instances found in env.", file=sys.stderr)
        sys.exit(2)

    conn = db_conn()
    ensure_schema(conn)

    for name, cfg in inst.items():
        base, key, kind = cfg["base"], cfg["key"], cfg["kind"]
        print(f"Ingesting from {name} ({kind}) @ {base}", flush=True)
        try:
            if kind == "sonarr":
                ingest_sonarr(conn, name, base, key)
            else:
                ingest_radarr(conn, name, base, key)
            conn.commit()
        except Exception as e:
            print(f"[error] {name}: {e}", file=sys.stderr)

    conn.close()
    print(f"Done. Wrote metadata into {DB_PATH}", flush=True)

if __name__ == "__main__":
    main()
