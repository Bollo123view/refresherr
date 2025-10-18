from __future__ import annotations
import os, re, time, json, logging, pathlib
from typing import Dict, List, Optional
from . import store

log = logging.getLogger("refresher.scanner")

def _load_routing(cfg: dict) -> List[Dict[str,str]]:
    routing = (cfg.get("routing") or [])
    # normalize path prefixes (no trailing slash)
    norm = []
    for r in routing:
        p = r.get("prefix", "").rstrip("/")
        t = r.get("type")
        if p and t:
            norm.append({"prefix": p, "type": t})
    # sort longest-first
    norm.sort(key=lambda x: len(x["prefix"]), reverse=True)
    return norm

def _route_for_path(path: str, routing: List[Dict[str,str]]) -> Optional[str]:
    for r in routing:
        if path.startswith(r["prefix"]):
            return r["type"]
    return None

def _relay_base_and_token() -> tuple[str,str]:
    base = os.environ.get("RELAY_BASE", "")
    token = os.environ.get("RELAY_TOKEN", "")
    return base, token

def enqueue_auto_action(path: str, title: str, route_type: str):
    base, token = _relay_base_and_token()
    if not base or not token:
        log.warning("Relay not configured; skipping auto action for %s", path)
        return
    # Build URL: RELAY_BASE already ends with /find
    params = {
        "token": token,
        "type": route_type,
        "scope": "auto",
        "term": title
    }
    # We keep it simple; the relay decides series/season/episodes/movie
    url = base + "?" + "&".join(f"{k}={store.url_encode(str(v))}" for k,v in params.items())
    store.enqueue_action(url=url, reason="auto-search", related_path=path)

def scan_once(cfg: dict):
    """Entry called by CLI. Walks symlink roots and marks ok/broken.
       When broken is detected, enqueue a smart 'auto' find action routed by cfg.routing.
    """
    roots: List[str] = cfg.get("scan", {}).get("roots", [])
    routing = _load_routing(cfg)
    dryrun = str(os.environ.get("DRYRUN","true")).lower() == "true"

    for root in roots:
        root = root.rstrip("/")
        for p in pathlib.Path(root).rglob("*"):
            if p.is_symlink():
                try:
                    target = os.readlink(p)
                    ok = os.path.exists(p.resolve())
                except Exception:
                    ok = False
                    target = None
                status = "ok" if ok else "broken"
                store.record_symlink(str(p), target, status)

                if status == "broken":
                    # derive display title from folder name (series or movie dir)
                    title = p.parent.name
                    rtype = _route_for_path(str(p), routing) or ""
                    if rtype:
                        enqueue_auto_action(str(p), title, rtype)
                    else:
                        log.info("No routing hit for %s; not enqueuing", p)

    if dryrun:
        log.info("DRYRUN=true: recorded statuses and queued actions but made no external changes.")
