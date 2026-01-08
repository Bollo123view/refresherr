import typer
from refresher.core.scanner import run_loop, one_scan
from refresher.core.store import get_pending, mark_sent
from refresher.core.orchestrator import get_orchestrator_state, set_orchestrator_enabled
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
    for action_id, url in pending:
        ok = False
        try:
            if url:
                requests.get(url, timeout=15)
                ok = True
        except requests.RequestException:
            ok = False
        mark_sent(action_id, ok)
        fired += 1
        time.sleep(delay)
    print({"fired": fired, "remaining": max(0, len(pending) - fired)})

@app.command()
def orchestrator_status():
    """Show the current auto-repair orchestrator status."""
    state = get_orchestrator_state()
    status = "ENABLED" if state["enabled"] else "DISABLED"
    print(f"Auto-repair orchestrator: {status}")
    if state.get("last_auto_run_utc"):
        print(f"Last automatic run: {state['last_auto_run_utc']}")
    print(f"Last updated: {state['updated_utc']}")

@app.command()
def orchestrator_toggle(enable: bool = typer.Option(..., "--enable/--disable", help="Enable or disable auto-repair")):
    """Toggle the auto-repair orchestrator on or off."""
    state = set_orchestrator_enabled(enable)
    status = "ENABLED" if state["enabled"] else "DISABLED"
    print(f"Auto-repair orchestrator: {status}")
    print(f"Updated: {state['updated_utc']}")

if __name__ == "__main__":
    app()

