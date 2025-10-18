# Refresherr Patch (auto-search + relay "auto" scope)

This bundle adds:
- **Relay `scope=auto`**: smart pick between Series/Season/Episodes or Movies search.
- **Scanner enqueue**: when a symlink is broken, queue a relay call with `scope=auto`,
  routed by `config.routing` (no symlink rewrites, read-only).
- **Store actions queue**: simple `actions` table + helpers.

## Files in this patch
- `services/research-relay/app.py`
- `app/refresher/core/scanner.py`
- `app/refresher/core/store.py`
- `config/config.yaml` (merge with your config if you already have one)

## Environment
Ensure your `.env` (or container env) provides:
```
DATA_DIR=/data
RELAY_TOKEN=...
RELAY_BASE=http://research-relay:5050/find
# pacing (optional)
RELAY_MIN_INTERVAL_SEC=5

# Relay instances
SONARR_TV_URL=http://sonarr-tv:8989
SONARR_TV_API=xxxx
SONARR_HAYU_URL=http://sonarr-hayu:8989
SONARR_HAYU_API=yyyy
RADARR_DOC_URL=http://radarr-doc:7878
RADARR_DOC_API=zzzz
RADARR_4K_URL=http://radarr-4k:7878
RADARR_4K_API=aaaa
```

## Deploy
1. Stop your app containers (scanner + relay).
2. Back up your code and `/opt/refresherr/data/symlinks.db` (optional).
3. Copy the patched files into your project preserving paths.
4. Start containers.
5. Trigger a scan. Broken symlinks will enqueue URLs like:
   `RELAY_BASE?token=...&type=sonarr_tv&scope=auto&term=Series%20Name`
6. Your existing action-replay loop should send these URLs, one by one.

## Test the relay directly
```
curl "http://localhost:5050/find?token=YOURTOKEN&type=sonarr_tv&scope=auto&term=The%20Office"
```

## Rollback
Restore your backed-up files/DB, or replace files from your repo.
