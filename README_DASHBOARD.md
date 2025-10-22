# Refresherr Dashboard (symlink-focused)

A tiny Flask app that shows **only symlinked** items from your `symlinks.db` and
lets you trigger the relay's **scope=auto** searches with one click.

## Files
- `services/dashboard/app.py`
- `services/dashboard/requirements.txt`
- `services/dashboard/templates/*.html`

## Compose snippet
Add this service to your `docker-compose.yml`:

```yaml
  dashboard:
    build:
      context: ./services/dashboard
    container_name: refresher-dashboard
    env_file:
      - ./.env
    environment:
      - DATA_DIR=/data
      - RELAY_BASE=${RELAY_BASE}
      - RELAY_TOKEN=${RELAY_TOKEN}
      - FLASK_SECRET=change-me
    volumes:
      - ./data:/data:ro
    ports:
      - "8088:8088"
    command: ["python", "app.py"]
    restart: unless-stopped
```

Then:
```bash
docker compose up -d --build dashboard
# visit http://localhost:8088/
```

## Notes
- Only **symlinked** items are listed in Movies/Episodes views.
- Broken symlinks view pulls from `symlinks.last_status='broken'` (read-only).
- Action buttons call the relay with `scope=auto` using `RELAY_BASE` & `RELAY_TOKEN` from your `.env`.
- This is read-only for your library; it does not modify files or symlinks.
