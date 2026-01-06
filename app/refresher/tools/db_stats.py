from __future__ import annotations

import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "/data/symlinks.db")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)

    # basic existence check
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "symlinks" not in tables:
        print("No symlinks table found in DB:", DB_PATH)
        return

    cols = {r[1] for r in conn.execute("PRAGMA table_info(symlinks)")}
    if "last_status" not in cols:
        print("symlinks table missing last_status column; columns:", sorted(cols))
        return

    print("DB:", DB_PATH)
    for status, cnt in conn.execute(
        "SELECT last_status, COUNT(*) FROM symlinks GROUP BY last_status ORDER BY COUNT(*) DESC"
    ):
        print(f"{status}\t{cnt}")

    print("\nTop broken parent folders (top 25):")
    try:
        parents: dict[str, int] = {}
        for (path,) in conn.execute("SELECT path FROM symlinks WHERE last_status='broken'"):
            parent = os.path.dirname(path)
            parents[parent] = parents.get(parent, 0) + 1

        for parent, cnt in sorted(parents.items(), key=lambda x: x[1], reverse=True)[:25]:
            print(f"{cnt}\t{parent}")
    except Exception as e:
        print("Couldn't compute parent folder summary:", e)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

