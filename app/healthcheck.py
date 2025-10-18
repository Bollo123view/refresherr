# app/healthcheck.py
import os, sys, json
from app.refresher.core.scanner import scan_once

def main():
    # Run a very fast, side-effect-free scan
    cfg = os.environ.get("CONFIG_PATH", "/app/config/config.yaml")
    res = scan_once(cfg)
    # Health: ok AND mount present
    ok = bool(res.get("ok")) and res.get("summary", {}).get("mount_ok", True)
    print(json.dumps(res.get("summary", {})))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

