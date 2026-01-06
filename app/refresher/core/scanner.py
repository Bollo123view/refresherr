from __future__ import annotations
import os, time, json, yaml, pathlib, urllib.parse
from typing import List, Tuple, Optional, Dict, Any
from .mounts import is_mount_present
from .relay_client import build_find_link, relay_from_env
from . import store
# Import central config module
import sys
# Add parent directory to path to import config module
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
# Import from refresher.config to maintain consistent module identity
try:
    from refresher.config import (
        load_config, route_for_path, apply_rewrites, RefresherrConfig,
        container_to_logical, logical_to_container
    )
except ImportError:
    # Fallback for different import contexts
    from config import (
        load_config, route_for_path, apply_rewrites, RefresherrConfig,
        container_to_logical, logical_to_container
    )

# Legacy helpers for backward compatibility (delegate to config module)

def _load_cfg_from_path(cfg_path: str) -> dict:
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def _load_routing(cfg: dict) -> List[Dict[str,str]]:
    routing = (cfg.get("routing") or [])
    norm = []
    for r in routing:
        p = r.get("prefix", "").rstrip("/")
        t = r.get("type")
        if p and t:
            norm.append({"prefix": p, "type": t})
    norm.sort(key=lambda x: len(x["prefix"]), reverse=True)
    return norm

def _route_for_path(path: str, routing: List[Dict[str,str]]) -> Optional[str]:
    for r in routing:
        if path.startswith(r["prefix"]):
            return r["type"]
    return None

def _load_scan_roots(cfg: dict) -> List[str]:
    return cfg.get("scan", {}).get("roots", [])

def _load_mount_checks(cfg: dict) -> List[str]:
    return cfg.get("scan", {}).get("mount_checks", [])

def rewrite_target(target: str, rewrites: List[Tuple[str,str]]) -> str:
    for src, dst in rewrites:
        if src and target.startswith(src):
            return target.replace(src, dst, 1)
    return target

def classify(path: str) -> tuple[str, str, Optional[int]]:
    # Lightweight classify - returns (kind, name, season)
    # Season extraction best-effort
    import re
    def _extract_season_from_path(p: str):
        parts = re.split(r"[\\/]", p)
        for seg in parts:
            m = re.match(r"(?i)^season[ _-]?(\d{1,2})$", seg)
            if m:
                return int(m.group(1))
            m2 = re.match(r"(?i)^s(\d{2})$", seg)
            if m2:
                return int(m2.group(1))
        return None

    season = _extract_season_from_path(path)
    if "/jelly/4k/" in path:
        name = pathlib.Path(path).parent.name
        return ("4k", name, season)
    if "/jelly/doc/" in path:
        name = pathlib.Path(path).parent.name
        return ("doc", name, season)
    if "/jelly/hayu/" in path:
        base = pathlib.Path(path).parent.parent
        return ("hayu", base.name, season)
    base = pathlib.Path(path).parent.parent
    return ("tv", base.name, season)

# Primary scan function

def scan_once(cfg_or_path: Any, dryrun: bool = True) -> dict:
    """
    Scan configured roots for symlinks, record statuses in DB, and enqueue relay find actions for broken symlinks.
    cfg_or_path: either a dict (already parsed YAML), a RefresherrConfig object, or a path string to YAML config.
    Returns a dict with summary.
    """
    # Initialize path_mappings for all code paths (empty list for legacy compatibility)
    path_mappings = []
    
    # Support new config module alongside legacy dict-based config
    if isinstance(cfg_or_path, RefresherrConfig):
        # Use new config module
        config = cfg_or_path
        roots = config.scan.roots
        mounts = config.scan.mount_checks
        rewrites = config.scan.rewrites
        routing = config.routing
        relay_base = config.relay.base_url
        relay_token = config.relay.token
        path_mappings = config.path_mappings
    elif isinstance(cfg_or_path, str):
        # Try loading with new config module first
        try:
            config = load_config(cfg_or_path)
            roots = config.scan.roots
            mounts = config.scan.mount_checks
            rewrites = config.scan.rewrites
            routing = config.routing
            relay_base = config.relay.base_url
            relay_token = config.relay.token
            path_mappings = config.path_mappings
        except Exception:
            # Fall back to legacy dict-based loading (no path_mappings support)
            cfg = _load_cfg_from_path(cfg_or_path)
            roots = _load_scan_roots(cfg)
            mounts = _load_mount_checks(cfg)
            rewrites = [(r.get("from"), r.get("to")) for r in cfg.get("scan", {}).get("rewrites", [])]
            routing = _load_routing(cfg)
            relay_base_env = cfg.get("relay", {}).get("base_env", "RELAY_BASE")
            relay_token_env = cfg.get("relay", {}).get("token_env", "RELAY_TOKEN")
            relay_base, relay_token = relay_from_env(relay_base_env, relay_token_env)
            # path_mappings remains empty list for legacy
    else:
        # Legacy dict-based config (no path_mappings support)
        cfg = cfg_or_path or {}
        roots = _load_scan_roots(cfg)
        mounts = _load_mount_checks(cfg)
        rewrites = [(r.get("from"), r.get("to")) for r in cfg.get("scan", {}).get("rewrites", [])]
        routing = _load_routing(cfg)
        relay_base_env = cfg.get("relay", {}).get("base_env", "RELAY_BASE")
        relay_token_env = cfg.get("relay", {}).get("token_env", "RELAY_TOKEN")
        relay_base, relay_token = relay_from_env(relay_base_env, relay_token_env)
        # path_mappings remains empty list for legacy

    # Mount checks
    for m in mounts:
        if not is_mount_present(m):
            summary = {"ok": False, "error": f"mount not present: {m}", "mount_ok": False}
            return {"ok": False, "summary": summary}

    broken = []
    examined = 0

    for root in roots:
        if not root:
            continue
        root_p = pathlib.Path(root)
        if not root_p.exists():
            continue
        for p in root_p.rglob("*"):
            # only consider files that are symlinks
            try:
                if not p.is_symlink():
                    continue
            except Exception:
                continue
            examined += 1
            target = None
            ok = False
            try:
                target = os.readlink(str(p))
                # Resolve relative targets against parent
                full = pathlib.Path(target)
                if not full.is_absolute():
                    full = (p.parent / full).resolve()
                ok = full.exists()
                resolved = str(full)
            except Exception:
                ok = False
                resolved = ""
            status = "ok" if ok else "broken"

            # Record in DB
            try:
                store.record_symlink(str(p), target, status)
            except Exception:
                # don't let DB errors stop scan
                pass

            if not ok:
                kind, name, season = classify(str(p))
                # routing decides find type - use new or legacy routing helper
                if isinstance(routing, list) and routing and len(routing) > 0 and hasattr(routing[0], 'prefix'):
                    # New config module routing
                    rtype = route_for_path(str(p), routing) or ""
                else:
                    # Legacy dict-based routing
                    rtype = _route_for_path(str(p), routing) or ""
                
                relay_url = ""
                if rtype and relay_base and relay_token:
                    # Build a find link via the relay
                    relay_url = build_find_link(relay_base, relay_token, rtype, name)
                    
                    # Only enqueue if NOT in dry run mode
                    if not dryrun:
                        try:
                            store.enqueue_action(url=relay_url, reason="auto-search", related_path=str(p))
                        except Exception:
                            pass
                
                # Build a payload row for manifest (includes route type and relay URL)
                broken.append((str(p), target, resolved, kind, name, season, rtype, relay_url))

    summary = {
        "ok": True,
        "broken_count": len(broken),
        "examined": examined,
        "dryrun": dryrun,
        "mount_ok": True
    }
    
    # Generate detailed manifest for dry run mode or provide sample
    manifest = []
    if broken:
        # Include more details in manifest
        for b in broken:
            container_path = b[0]
            logical_path = container_to_logical(container_path, path_mappings) if path_mappings else container_path
            item = {
                "path": container_path,
                "target": b[1],
                "resolved": b[2],
                "kind": b[3],
                "name": b[4],
                "season": b[5] if len(b) > 5 else None,
                "route_type": b[6] if len(b) > 6 else None,
                "relay_url": b[7] if len(b) > 7 else None
            }
            # Include logical path if different from container path
            if logical_path != container_path:
                item["logical_path"] = logical_path
            
            # Add action description for dry run manifest
            if dryrun and item["relay_url"]:
                item["dry_run_action"] = f"Would enqueue repair via {item['route_type']}"
            elif not dryrun and item["relay_url"]:
                item["action"] = f"Enqueued repair via {item['route_type']}"
            
            manifest.append(item)
        
        # For backward compatibility, keep sample field with limited entries
        summary["sample"] = manifest[:20]
        
        # In dry run mode, include full manifest
        if dryrun:
            summary["manifest"] = manifest
            summary["manifest_summary"] = {
                "total_broken": len(broken),
                "would_enqueue": sum(1 for item in manifest if item.get("relay_url")),
                "by_kind": {},
                "by_route": {}
            }
            # Count by kind and route
            for item in manifest:
                kind = item.get("kind", "unknown")
                route = item.get("route_type", "no_route")
                summary["manifest_summary"]["by_kind"][kind] = summary["manifest_summary"]["by_kind"].get(kind, 0) + 1
                summary["manifest_summary"]["by_route"][route] = summary["manifest_summary"]["by_route"].get(route, 0) + 1

    return {"ok": True, "summary": summary}

# CLI helpers expected by app/cli.py

def one_scan(cfg_path: Optional[str] = None, dryrun: bool = True):
    """Run a single dry-run scan; kept for CLI compatibility.

    If cfg_path is not provided the CONFIG_FILE env var is used (default /config/config.yaml).
    """
    if cfg_path is None:
        cfg_path = os.environ.get("CONFIG_FILE", "/config/config.yaml")
    return scan_once(cfg_path, dryrun=dryrun)

def run_loop(cfg_path: Optional[str] = None, interval: Optional[int] = None, dryrun: Optional[bool] = None):
    """
    Run the scanner in a loop. Interval (seconds) read from SCAN_INTERVAL env (default 300) if not provided.
    Honor DRYRUN env var (true/false) if dryrun is not provided.
    """
    if cfg_path is None:
        cfg_path = os.environ.get("CONFIG_FILE", "/config/config.yaml")
    if interval is None:
        try:
            interval = int(os.environ.get("SCAN_INTERVAL", "300"))
        except Exception:
            interval = 300
    if dryrun is None:
        dryrun = str(os.environ.get("DRYRUN", "true")).lower() == "true"

    while True:
        try:
            res = scan_once(cfg_path, dryrun=dryrun)
            # simple console summary
            s = res.get("summary", {})
            print(f"[refresher] scan: broken={s.get('broken_count',0)} examined={s.get('examined',0)} dryrun={s.get('dryrun')}", flush=True)
        except Exception as e:
            print(f"[refresher] scan_loop error: {e}", flush=True)
        time.sleep(interval)
