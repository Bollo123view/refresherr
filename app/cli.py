import typer
from refresher.core.scanner import run_loop, one_scan

app = typer.Typer(add_completion=False)

@app.command()
def run():
    """"Run the refresher in a loop (interval from env/config).""""
    run_loop()

@app.command()
def scan_once():
    """"Run a single scan and exit (useful for testing/health).""""
    one_scan()

if __name__ == '__main__':
    app()
