# Refresherr Manual Tools (Safe Mode)

These tools are **manual-first** and do **not** create symlinks, quarantine, or delete anything.

They work even if the refresher container doesn't have the `sqlite3` binary installed (they use Python's sqlite3).

## Install

Copy the `app/refresher/tools/` folder into your repo at:

`/opt/refresherr/app/refresher/tools/`

(merge it into the existing `app/refresher/` package)

## Usage

### 1) DB status counts

Run inside the refresher container:

```bash
docker compose exec refresher python -m refresher.tools.db_stats
```

### 2) Queue repairs (MANUAL)

Queues actions for broken symlinks into the `actions` table.

Set routing + relay env vars (edit your `.env` / compose env):

```bash
RELAY_BASE=http://research-relay:5050/find
RELAY_TOKEN=YOURTOKEN
ROUTE_MAP=/opt/media/jelly/tv=sonarr_tv,/opt/media/jelly/hayu=sonarr_hayu,/opt/media/jelly/doc=radarr_doc,/opt/media/jelly/4k=radarr_4k
```

Then:

```bash
docker compose exec -e QUEUE_LIMIT=25 refresher python -m refresher.tools.queue_repairs
```

This prints the queued items.

### 3) Process queued actions (MANUAL)

This will send pending actions to the relay (no deletes/quarantine).

```bash
docker compose exec -e ACTIONS_MAX=25 refresher python -m refresher.tools.process_actions
```

Dry-run:

```bash
docker compose exec -e ACTIONS_DRY_RUN=1 refresher python -m refresher.tools.process_actions
```

## Notes

- These tools are intended as the "safe stepping stone" before enabling any automatic behaviour.
- Once you're happy with terms/routing, we can wire the dashboard buttons and (later) optional quarantine/delete cooldowns.
