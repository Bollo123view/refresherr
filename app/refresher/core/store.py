import os, sqlite3, time
from typing import Optional, Iterable, Tuple

def _db_path() -> str:
    data_dir = os.environ.get("DATA_DIR", "/data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "history.db")

def _conn():
    con = sqlite3.connect(_db_path())
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

def init_schema():
    con = _conn()
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS runs(
      id INTEGER PRIMARY KEY,
      ts INTEGER NOT NULL,
      dryrun INTEGER NOT NULL,
      broken_count INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS items(
      id INTEGER PRIMARY KEY,
      run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
      path TEXT, target TEXT, resolved TEXT,
      kind TEXT, name TEXT, season INTEGER
    );
    CREATE TABLE IF NOT EXISTS actions(
      id INTEGER PRIMARY KEY,
      kind TEXT NOT NULL,
      name TEXT NOT NULL,
      season INTEGER,
      scope TEXT NOT NULL,            -- series|season|movie
      url TEXT,
      status TEXT NOT NULL DEFAULT 'pending',  -- pending|fired|failed
      last_ts INTEGER,
      times_fired INTEGER NOT NULL DEFAULT 0,
      UNIQUE(kind, name, season, scope)
    );
    """)
    con.commit()
    con.close()

def log_run(dryrun: bool, broken_count: int) -> int:
    con = _conn()
    cur = con.cursor()
    cur.execute("INSERT INTO runs(ts, dryrun, broken_count) VALUES(?,?,?)",
                (int(time.time()), 1 if dryrun else 0, broken_count))
    run_id = cur.lastrowid
    con.commit()
    con.close()
    return run_id

def add_items(run_id: int, rows: Iterable[Tuple[str,str,str,str,str,Optional[int]]]):
    # rows: (path, target, resolved, kind, name, season)
    con = _conn()
    cur = con.cursor()
    cur.executemany(
        "INSERT INTO items(run_id, path, target, resolved, kind, name, season) VALUES(?,?,?,?,?,?,?)",
        ((run_id, *row) for row in rows)
    )
    con.commit()
    con.close()

def upsert_action(kind: str, name: str, season: Optional[int], scope: str, url: str):
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO actions(kind,name,season,scope,url,status,last_ts,times_fired)
        VALUES(?,?,?,?,?, 'pending', ?, 0)
        ON CONFLICT(kind,name,season,scope) DO UPDATE SET
          url=excluded.url
    """, (kind, name, season, scope, url, int(time.time())))
    con.commit()
    con.close()

def mark_fired(kind: str, name: str, season: Optional[int], scope: str, ok: bool):
    con = _conn()
    cur = con.cursor()
    cur.execute("""
      UPDATE actions SET
        status = CASE WHEN ? THEN 'fired' ELSE 'failed' END,
        last_ts = ?,
        times_fired = times_fired + CASE WHEN ? THEN 1 ELSE 0 END
      WHERE kind=? AND name=? AND scope=? AND (season IS ? OR season = ?)
    """, (1 if ok else 0, int(time.time()), 1 if ok else 0,
          kind, name, scope, season, season))
    con.commit()
    con.close()

def get_pending(limit: int = 50):
    con = _conn()
    cur = con.cursor()
    cur.execute("""
      SELECT kind,name,season,scope,url FROM actions
      WHERE status='pending'
      ORDER BY last_ts NULLS FIRST, id ASC
      LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    con.close()
    return rows

