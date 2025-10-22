# Metadata Ingest for Refresherr

This module imports **current library metadata** from your existing *arr instances
without scraping the internet, and stores it in the same DB as Refresherr (`DATA_DIR/symlinks.db`).

It creates/updates these tables:
- `movies` / `movie_files` (Radarr)
- `series` / `episode_files` (Sonarr)

It also tries to **link files to your symlinks** by matching `original_path` to the `symlinks.last_target` value.

## Environment expected
The module auto-discovers instances from your `.env`:
```
DATA_DIR=/data
SONARR_TV_URL=...
SONARR_TV_API=...
SONARR_HAYU_URL=...
SONARR_HAYU_API=...
RADARR_DOC_URL=...
RADARR_DOC_API=...
RADARR_4K_URL=...
RADARR_4K_API=...
```
(Any `SONARR_*_URL` paired with `SONARR_*_API`, and same for `RADARR_*` will be ingested.)

## How to run
Inside your project directory:
```bash
# copy files in place
unzip -o ~/Downloads/ingest_bundle.zip -d .

# run ingest inside the refresher container so it sees the same DATA_DIR
docker compose exec refresher python -m refresher.ingest
```

You should see lines like:
```
Ingesting from sonarr_tv (sonarr) @ http://sonarr-tv:8989
Ingesting from radarr_doc (radarr) @ http://radarr-doc:7878
Done. Wrote metadata into /data/symlinks.db
```

## Notes
- This does **not** modify symlinks (read-only).
- It uses gentle retries for 429/50x responses.
- If you later change how you want to link symlinks↔files, we can add a join using patterns or a small mapping table.
