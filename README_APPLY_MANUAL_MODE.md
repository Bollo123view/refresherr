# Refresherr Manual Mode Patch

This patch keeps Refresherr **manual-safe**:
- Scanner only records symlink status into SQLite.
- **No auto-queue**, **no delete**, **no quarantine**.
- Dashboard "Repair" button now works: it **queues** a relay action into `actions` (pending).
- Refresher loop will process pending actions by calling the relay URL (no symlink removal).

## Apply

From the root of your `refresherr/` repo:

```bash
git apply refresherr_manual_mode.patch
```

(Or, if you don't use git, you can apply it with the `patch` tool:)

```bash
patch -p1 < refresherr_manual_mode.patch
```

## Configure

1) Set these in your `.env` (dashboard needs them):

- `RELAY_BASE` e.g. `http://research-relay:5050/find` (or whatever port you mapped)
- `RELAY_TOKEN` must match the relay service

2) Keep manual-safe mode (default):

- `AUTO_ENQUEUE=0`

## Run

```bash
docker compose up -d --build
```

Then open the dashboard and use **Broken → Repair** to queue actions.

## Notes

- This patch intentionally **does not** attempt to create/repair symlinks. Your RDTClient workflow owns that.
- If you later want "quarantine" mode, we can add it behind a strict feature flag.
