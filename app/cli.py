import typer
from refresher.core.scanner import run_loop, one_scan
from refresher.core.store import get_pending, mark_fired
import requests, time

app = typer.Typer(add_completion=False)

@app.command()
def run():
    """Run the refresher in a loop (interval from env/config)."""
    run_loop()

@app.command()
def scan_once():
    """Run a single scan and exit (useful for testing/health)."""
    one_scan()

@app.command()
def replay_actions(limit: int = 50, delay: float = 2.0):
    """Trigger pending Sonarr/Radarr searches from the DB queue."""
    pending = get_pending(limit=limit)
    fired = 0
    for kind, name, season, scope, url in pending:
        ok = False
        try:
            if url:
                requests.get(url, timeout=15)
                ok = True
        except requests.RequestException:
            ok = False
        mark_fired(kind, name, season, scope, ok)
        fired += 1
        time.sleep(delay)
    print({"fired": fired, "remaining": max(0, len(pending) - fired)})
