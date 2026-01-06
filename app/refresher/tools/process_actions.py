"""Process actions tool - uses central DB module."""
from __future__ import annotations
import os, time, sqlite3, requests
from app.refresher.core import db

DB_PATH = os.environ.get("DB_PATH", "/data/symlinks.db")

def main() -> None:
    conn = db.get_connection(DB_PATH)
    db.initialize_schema(conn)

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
