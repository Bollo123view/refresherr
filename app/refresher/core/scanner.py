# app/refresher/core/scanner.py
from __future__ import annotations

import os
import re
import sys
import time
import json
import stat
import logging
from typing import Dict, Iterable, List, Optional

try:
    import yaml  # type: ignore
except Exception:
    print("ERROR: pyyaml is required. pip install pyyaml", file=sys.stderr)
    raise

# ----- Optional Discord notifier (graceful if absent) ------------------------
def _import_notifier():
    try:
        from refresher.core.notifier import post_discord  # type: ignore
        return post_discord
    except Exception:
        try:
            from app.refresher.core.notifier import post_discord  # type: ignore
            return post_discord
        except Exception:
            return None

post_discord = _import_notifier()

# ----- Store (DB) import (graceful fallback to no-op if missing) -------------
class _NoDB:
    def init_schema(self): pass
    def begin_scan(self) -> Optional[int]: return None
    def add_items(self, scan_id: int, items: List[Dict]): pass
    def finalize_scan(self, scan_id: int, summary: Dict): pass

def _import_store():
    try:
        from refresher.core import store  # type: ignore
        return store
    except Exception:
        try:
            from app.refresher.core import store  # type: ignore
            return store
        except Exception:
            return _NoDB()

store = _import_store()

log = logging.getLogger("refresher.scanner")
logging.basicConfig(
    level=os.environ.get("REFRESHER_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ===== Config ================================================================

DEFAULT_CONFIG_PATH = "/config/config.yaml"  # matches your compose bind

def load_config(path: str = DEFAULT_CONFIG_PATH) -> Dict:
    """Load YAML config. Returns {} if missing so we can still run."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return raw
    except FileNotFoundError:
        log.warning("Config not found at %s; proceeding with env defaults", path)
        return {}
    except Exception as e:
        log.error("Failed to load config %s: %s", path, e)
        return {}

# ===== Mount detection =======================================================

def _is_path_mounted_linux(target: str) -> bool:
    """Check /proc/self/mountinfo for an exact mountpoint match."""
    target = os.path.abspath(target)
    try:
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        # Fallback: device id differs from parent
        st = os.stat(target)
        parent = os.path.abspath(os.path.join(target, ".."))
        st_parent = os.stat(parent)
        return st.st_dev != st_parent.st_dev

    for line in lines:
        try:
            left, _, _right = line.partition(" - ")
            parts = left.split()
            if len(parts) >= 5:
                mp = parts[4]
                if os.path.abspath(mp) == target:
                    return True
        except Exception:
            continue
    return False

def is_mount_present(path: str) -> bool:
    try:
        if not os.path.isdir(path):
            return False
        return _is_path_mounted_linux(path)
    except FileNotFoundError:
        return False
    except Exception as e:
        log.warning("Mount check fallback for %s due to: %s", path, e)
        try:
            os.listdir(path)
            return True
        except Exception:
            return False

# ===== Symlink discovery & classification ====================================

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}

def iter_symlinks(root: str) -> Iterable[str]:
    """Yield absolute paths to symlinks under root (recursive)."""
    root = os.path.abspath(root)
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.lstat(p)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(st.st_mode):
                yield p

_title_scrub = re.compile(r"[._]+")
_episode_pat = re.compile(
    r"""(?ix)
    (?:s(?P<season>\d{1,2})[ ._-]*e(?P<episode>\d{1,3}))
    |
    (?:season[ ._-]?(?P<season2>\d{1,2})[ ._-]*episode[ ._-]?(?P<episode2>\d{1,3}))
    """
)

def classify_symlink(link_path: str) -> Dict:
    """Classify a symlink: resolve target, ext, best-effort search query."""
    item: Dict = {
        "path": link_path,
        "type": "symlink",
        "broken": False,
        "ext": os.path.splitext(link_path)[1].lower(),
        "target": None,
        "query": None,
        "season": None,
        "episode": None,
        "size_bytes": None,
        "mtime_ns": None,
    }
    try:
        target = os.readlink(link_path)
        if not os.path.isabs(target):
            target = os.path.abspath(os.path.join(os.path.dirname(link_path), target))
        item["target"] = target
        if not os.path.exists(target):
            item["broken"] = True
        else:
            try:
                st = os.stat(target)
                item["size_bytes"] = st.st_size
                item["mtime_ns"] = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
            except Exception:
                item["size_bytes"] = None
                item["mtime_ns"] = None
    except OSError:
        item["broken"] = True

    base = os.path.basename(link_path)
    name = os.path.splitext(base)[0]
    m = _episode_pat.search(name)
    if m:
        season = m.group("season") or m.group("season2")
        episode = m.group("episode") or m.group("episode2")
        head = _episode_pat.sub("", name).strip("-_. ")
        head = _title_scrub.sub(" ", head).strip()
        if season and episode:
            item["season"] = int(season)
            item["episode"] = int(episode)
            item["query"] = f"{head} S{int(season):02d}E{int(episode):02d}"
    else:
        item["query"] = _title_scrub.sub(" ", name).strip()

    return item

# ===== Relay "find" link builder =============================================

def normalise_base(url: str) -> str:
    if not url:
        return url
    url = url.rstrip("/")
    if url.endswith("/find"):
        url = url[:-5]
    return url

def build_find_link(base: str, token: str, find_type: str, term: str) -> str:
    from urllib.parse import urlencode, quote
    base = normalise_base(base)
    qs = urlencode({"type": find_type, "term": term, "token": token}, quote_via=quote)
    return f"{base}/find?{qs}"

# ===== Scan Once + DB persistence ============================================

def scan_once(config_path: str = DEFAULT_CONFIG_PATH) -> Dict:
    """
    Perform a single scan (non-destructive):
      - Verify mount presence
      - Walk symlinks under SYMLINK_ROOT
      - Classify each; collect broken ones
      - Persist snapshot/history via store (if present)
      - Return summary + prebuilt 'find' actions
    """
    t0 = time.time()
    cfg = load_config(config_path)

    env = os.environ
    mount_root = env.get("MOUNT_ROOT") or cfg.get("paths", {}).get("mount_root") or "/mnt/rd"
    symlink_root = env.get("SYMLINK_ROOT") or cfg.get("paths", {}).get("symlink_root") or "/mnt/symlinks"

    relay_base = env.get("RELAY_BASE") or cfg.get("relay", {}).get("base", "")
    relay_token_env = cfg.get("relay", {}).get("token_env", "RELAY_TOKEN")
    relay_token = env.get(relay_token_env, "")

    include_exts: set = set(map(str.lower, cfg.get("scan", {}).get("extensions", []))) or VIDEO_EXTS
    include_exts = {e if e.startswith(".") else f".{e}" for e in include_exts}

    # Mount check
    mount_ok = is_mount_present(mount_root)
    if not mount_ok:
        log.warning("Mount %s not present. Aborting scan.", mount_root)
        return {"ok": False, "reason": "mount_absent", "mount_root": mount_root}

    # Begin DB scan (if store available)
    scan_id = None
    try:
        store.init_schema()
        scan_id = getattr(store, "begin_scan", lambda: None)()
    except Exception:
        scan_id = None

    # Walk symlinks
    items: List[Dict] = []
    count_all = 0
    broken: List[Dict] = []
    ok_files = 0
    for link in iter_symlinks(symlink_root):
        count_all += 1
        item = classify_symlink(link)
        if item["ext"] and item["ext"] not in include_exts:
            continue
        items.append(item)
        if item["broken"]:
            broken.append(item)
        else:
            ok_files += 1

    # Persist items into DB (store handles ok/broken/repairing + FTS)
    if scan_id is not None and hasattr(store, "add_items"):
        try:
            store.add_items(scan_id, items)  # 'repairing' is preserved inside store
        except Exception:
            pass

    # Summarise + duration
    summary = {
        "ok": True,
        "mount_ok": mount_ok,
        "scanned": count_all,
        "ok_files": ok_files,
        "broken": len(broken),
        "duration_s": round(time.time() - t0, 3),
    }

    if scan_id is not None and hasattr(store, "finalize_scan"):
        try:
            store.finalize_scan(scan_id, summary)
        except Exception:
            pass

    # Prepare “find” actions (not executed here)
    actions: List[Dict] = []
    if relay_base and relay_token and broken:
        for b in broken:
            q = (b.get("query") or os.path.basename(b["path"]))
            find_type = "sonarr_tv" if (b.get("season") is not None or " S" in (q or "").upper()) else "radarr_doc"
            url = build_find_link(relay_base, relay_token, find_type, q)
            payload = {
                "kind": "find",
                "query": q,
                "type": find_type,
                "url": url,
                "path": b["path"],
            }
            actions.append(payload)
            # If your store has upsert_action you can persist these:
            try:
                if hasattr(store, "upsert_action"):
                    store.upsert_action(kind="find", key=b["path"], payload=json.dumps(payload))
            except Exception:
                pass

    # Optional Discord summary — ONLY when broken > 0
    notify = str(os.getenv("DISCORD_NOTIFY", "0")).strip().lower() in {"1", "true", "yes", "on"}
    if notify and summary["broken"] > 0 and post_discord:
        msg = (
            f"Refresher scan: **{summary['scanned']}** symlinks | "
            f"✅ {summary['ok_files']} ok | ❌ {summary['broken']} broken | "
            f"mount_ok={summary.get('mount_ok', True)}"
        )
        if actions:
            msg += f" | queued actions: {len(actions)}"
        try:
            post_discord(msg)
        except Exception:
            pass

    # Friendly log
    if broken:
        log.info("Scan summary: %d symlinks; %d ok; %d broken", count_all, ok_files, len(broken))
        for a in actions[:10]:
            log.info("Broken: %s -> queued find: %s", a["path"], a["url"])
        if len(actions) > 10:
            log.info("…and %d more", len(actions) - 10)
    else:
        log.info("Scan summary: %d symlinks; %d ok; 0 broken", count_all, ok_files)

    return {"ok": True, "summary": summary, "actions": actions}

# ===== CLI entrypoint + legacy shims =========================================

def _as_bool(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Refresher scanner (single run)")
    ap.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config.yaml")
    ap.add_argument("--json", action="store_true", help="Emit JSON summary to stdout")
    args = ap.parse_args()

    res = scan_once(args.config)
    if args.json:
        print(json.dumps(res, indent=2, sort_keys=True))
    if not res.get("ok"):
        sys.exit(2 if res.get("reason") == "mount_absent" else 1)

# Legacy wrappers expected by cli.py
def one_scan(config_path: Optional[str] = None):
    return scan_once(config_path or DEFAULT_CONFIG_PATH)

def run_loop(interval_seconds: int = 300, config_path: Optional[str] = None):
    cfg_path = config_path or DEFAULT_CONFIG_PATH
    try:
        interval_seconds = int(interval_seconds)
    except Exception:
        interval_seconds = 300
    while True:
        try:
            scan_once(cfg_path)
        except Exception as e:
            log.exception("run_loop scan error: %s", e)
        time.sleep(interval_seconds)

if __name__ == "__main__":
    main()

