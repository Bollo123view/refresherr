import os, time, csv, io, yaml, re
from dataclasses import dataclass
from typing import List, Tuple
from .mounts import is_mount_present
from .notifier import post_discord_simple, post_discord_file, discord_webhook_url_from_env
from .relay_client import relay_from_env, build_find_link
from .history import add_events

@dataclass
class Config:
    roots: List[str]
    rewrites: List[Tuple[str,str]]
    mount_checks: List[str]
    discord_env: str
    relay_base_env: str
    relay_token_env: str

def load_config() -> Config:
    cfg_path = os.environ.get("CONFIG_FILE", "/config/config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    roots = raw.get("scan", {}).get("roots", [])
    rewrites = [(x.get("from"), x.get("to")) for x in raw.get("scan", {}).get("rewrites", [])]
    mounts = raw.get("scan", {}).get("mount_checks", [])
    discord_env = raw.get("notifications", {}).get("discord_webhook_env", "DISCORD_WEBHOOK")
    relay_base_env = raw.get("relay", {}).get("base_env", "RELAY_BASE")
    relay_token_env = raw.get("relay", {}).get("token_env", "RELAY_TOKEN")
    return Config(roots, rewrites, mounts, discord_env, relay_base_env, relay_token_env)

def rewrite_target(target: str, rewrites: List[Tuple[str,str]]) -> str:
    for src, dst in rewrites:
        if src and target.startswith(src):
            return target.replace(src, dst, 1)
    return target

def classify(path: str):
    if "/jelly/4k/" in path:
        return ("4k", os.path.basename(os.path.dirname(path)))
    if "/jelly/doc/" in path:
        return ("doc", os.path.basename(os.path.dirname(path)))
    if "/jelly/hayu/" in path:
        base = os.path.dirname(os.path.dirname(path))
        return ("hayu", os.path.basename(base))
    base = os.path.dirname(os.path.dirname(path))
    return ("tv", os.path.basename(base))

def scan_once(cfg: Config, dryrun: bool = True) -> dict:
    for m in cfg.mount_checks:
        if not is_mount_present(m):
            return {"ok": False, "error": f"mount not present: {m}"}

    broken = []
    for root in cfg.roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                full = os.path.join(dirpath, name)
                if not os.path.islink(full):
                    continue
                try:
                    target = os.readlink(full)
                except OSError:
                    target = ""
                resolved = rewrite_target(target, cfg.rewrites)
                if not os.path.exists(resolved):
                    kind, showname = classify(full)
                    broken.append((full, target, resolved, kind, showname))

    summary = {"ok": True, "broken_count": len(broken), "dryrun": dryrun}
    webhook = discord_webhook_url_from_env(cfg.discord_env)
    base_url, token = relay_from_env(cfg.relay_base_env, cfg.relay_token_env)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Type","Name","Path","Target","Resolved","FindLink"])
    now = int(time.time())
    evt_rows = []
    for (p, t, r, kind, name) in broken:
        link_type = {"tv":"sonarr_tv","hayu":"sonarr_hayu","doc":"radarr_doc","4k":"radarr_4k"}.get(kind,"sonarr_tv")
        find_link = build_find_link(base_url, token, link_type, name) if base_url and token else ""
        w.writerow([kind, name, p, t, r, find_link])
        evt_rows.append((now, p, t, kind, name, "detected", "dryrun" if dryrun else "delete"))
    csv_bytes = buf.getvalue().encode("utf-8")

    if webhook:
        post_discord_simple(webhook, f"ðŸ§ª refresher scan (dry-run={str(dryrun).lower()}): {len(broken)} broken symlinks")
        if broken:
            post_discord_file(webhook, "refresher_broken.csv", csv_bytes, "Full report")

    if evt_rows:
        add_events(evt_rows)

    if not dryrun:
        for (p, _, _, _, _) in broken:
            try: os.remove(p)
            except OSError: pass

    return summary

def one_scan():
    cfg = load_config()
    dry = os.environ.get("DRYRUN","true").lower() == "true"
    res = scan_once(cfg, dryrun=dry)
    print(res)

def run_loop():
    cfg = load_config()
    dry = os.environ.get("DRYRUN","true").lower() == "true"
    interval = int(os.environ.get("SCAN_INTERVAL","86400"))
    while True:
        scan_once(cfg, dryrun=dry)
        time.sleep(interval)
