from __future__ import annotations
import os, time, sqlite3, requests

DB_PATH = os.environ.get("DB_PATH", "/data/symlinks.db")

def ensure_actions_schema(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "actions" not in tables:
        conn.execute("""
            CREATE TABLE actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_utc INTEGER,
                url TEXT,
                reason TEXT,
                related_path TEXT,
                status TEXT DEFAULT 'pending',
                last_error TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_related_path ON actions(related_path)")
        conn.commit()
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(actions)")}
    for col, ddl in [
        ("created_utc","created_utc INTEGER"),
        ("url","url TEXT"),
        ("reason","reason TEXT"),
        ("related_path","related_path TEXT"),
        ("status","status TEXT DEFAULT 'pending'"),
        ("last_error","last_error TEXT"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE actions ADD COLUMN {ddl}")
    conn.commit()

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    ensure_actions_schema(conn)

    max_send = int(os.environ.get("ACTIONS_MAX", "25"))
    timeout = float(os.environ.get("ACTIONS_TIMEOUT", "15"))
    dry = os.environ.get("ACTIONS_DRY_RUN", "0") == "1"

    cols = {r[1] for r in conn.execute("PRAGMA table_info(actions)")}
    if "url" not in cols or "status" not in cols:
        raise SystemExit("actions table missing url/status columns; cannot process")

    rows = conn.execute(
        "SELECT id, url FROM actions WHERE status='pending' ORDER BY created_utc ASC LIMIT ?",
        (max_send,)
    ).fetchall()

    if not rows:
        print("No pending actions.")
        return

    sent = 0
    failed = 0

    for action_id, url in rows:
        if dry:
            print(f"DRY: would GET {url}")
            continue

        try:
            r = requests.get(url, timeout=timeout)
            if 200 <= r.status_code < 300:
                conn.execute("UPDATE actions SET status='sent', last_error=NULL WHERE id=?", (action_id,))
                conn.commit()
                sent += 1
                print(f"SENT: {action_id} {url}")
            else:
                msg = f"HTTP {r.status_code}"
                conn.execute("UPDATE actions SET status='failed', last_error=? WHERE id=?", (msg, action_id))
                conn.commit()
                failed += 1
                print(f"FAIL: {action_id} {msg} {url}")
        except Exception as e:
            conn.execute("UPDATE actions SET status='failed', last_error=? WHERE id=?", (str(e), action_id))
            conn.commit()
            failed += 1
            print(f"FAIL: {action_id} {e} {url}")

    print(f"\nDone. sent={sent} failed={failed} pending_checked={len(rows)}")

if __name__ == "__main__":
    main()
