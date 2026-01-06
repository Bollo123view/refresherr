from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests

# ---- Env ----
SHOW = os.environ.get("REPAIR_SHOW", "").strip()
SEASON = os.environ.get("REPAIR_SEASON", "").strip()  # int as str

# Library layout
LIB_ROOT_TV = os.environ.get("LIB_ROOT_TV", "/opt/media/jelly/tv").rstrip("/")
SEASON_DIR_FMT = os.environ.get("SEASON_DIR_FMT", "Season {n}")  # e.g. "Season 2"

# Quarantine (moves ONLY broken symlinks)
QUAR_BASE = os.environ.get("QUAR_BASE", "/opt/media/jelly/.quarantine").rstrip("/")

# Safety / pacing
DRY_RUN = os.environ.get("REPAIR_DRY_RUN", "1") == "1"
MAX_MOVE = int(os.environ.get("REPAIR_MAX_MOVE", "200"))  # cap per run
SLEEP_BETWEEN = float(os.environ.get("REPAIR_SLEEP", "0.2"))

# Threshold: only do SeasonSearch when missing >= threshold (default 3 => "more than 2")
SEASON_SEARCH_THRESHOLD = int(os.environ.get("SEASON_SEARCH_THRESHOLD", "3"))

# Sonarr (direct)
SONARR_URL = os.environ.get("SONARR_TV_URL", "").rstrip("/")
SONARR_API = os.environ.get("SONARR_TV_API", "")

SONARR_TIMEOUT = float(os.environ.get("SONARR_TIMEOUT", "25"))
SONARR_WAIT = float(os.environ.get("SONARR_WAIT", "1.0"))

SXXEYY_RE = re.compile(r"\bS(?P<s>\d{1,2})E(?P<e>\d{1,3})\b", re.IGNORECASE)
X_RE = re.compile(r"\b(?P<s>\d{1,2})x(?P<e>\d{2,3})\b", re.IGNORECASE)


def _norm_title(s: str) -> str:
    """
    Aggressive normalization so folder naming differences don't break matching:
      "Star Trek - Deep Space Nine" == "Star Trek: Deep Space Nine"
    """
    s = (s or "").strip().lower()
    s = re.sub(r"\s+\(\d{4}\)$", "", s)  # strip trailing (YYYY)
    s = s.replace("&", "and")
    s = re.sub(r"[:\-–—]", " ", s)       # colon/dash variants -> space
    s = re.sub(r"[^\w\s]", "", s)        # drop other punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _sonarr_headers() -> Dict[str, str]:
    return {"X-Api-Key": SONARR_API, "Content-Type": "application/json"}


def _sonarr_get(path: str, params: Dict[str, Any] | None = None) -> requests.Response:
    return requests.get(f"{SONARR_URL}{path}", headers=_sonarr_headers(), params=params or {}, timeout=SONARR_TIMEOUT)


def _sonarr_post(path: str, payload: Dict[str, Any]) -> requests.Response:
    return requests.post(f"{SONARR_URL}{path}", headers=_sonarr_headers(), json=payload, timeout=SONARR_TIMEOUT)


def resolve_series_id(title_or_folder: str, season_path: Path) -> Optional[int]:
    """
    Resolve series id without extra env vars:
    1) normalized title exact match
    2) normalized contains match
    3) match by Sonarr series.path folder name (basename), normalized
    """
    r = _sonarr_get("/api/v3/series")
    r.raise_for_status()

    wanted = _norm_title(title_or_folder)
    wanted_folder = _norm_title(season_path.parent.name)  # show folder name
    best: Optional[dict] = None

    for s in r.json() or []:
        t = _norm_title(s.get("title", ""))
        if t == wanted or t == wanted_folder:
            return int(s["id"])

        # folder-name match via series.path
        sp = s.get("path") or ""
        base = _norm_title(Path(sp).name) if sp else ""
        if base and (base == wanted_folder or base == wanted):
            return int(s["id"])

        if wanted and wanted in t:
            best = best or s
        if wanted_folder and wanted_folder in t:
            best = best or s

    if best and best.get("id"):
        return int(best["id"])
    return None


def is_broken_symlink(p: Path) -> bool:
    if not p.is_symlink():
        return False
    try:
        target = os.readlink(p)
        if not os.path.isabs(target):
            target = str((p.parent / target).resolve())
        return not os.path.exists(target)
    except OSError:
        return True


def quarantine_dest(src: Path) -> Path:
    # Mirror absolute path under QUAR_BASE
    return Path(QUAR_BASE + str(src))


def find_broken_symlinks(season_path: Path) -> list[Path]:
    broken: list[Path] = []
    for p in season_path.rglob("*"):
        if p.is_symlink() and is_broken_symlink(p):
            broken.append(p)
    return broken


def quarantine_season_path(season_path: Path) -> Path:
    return Path(QUAR_BASE + str(season_path))


def list_quarantine_items_for_season(season_path: Path) -> list[Path]:
    """
    If we've already quarantined items, they're mirrored under:
      QUAR_BASE + <absolute season_path>
    We use this list to decide what to search for even when the season folder is now clean.
    """
    qp = quarantine_season_path(season_path)
    if not qp.exists():
        return []
    items: list[Path] = []
    for p in qp.rglob("*"):
        if p.is_file() or p.is_symlink():
            items.append(p)
    return items


def parse_episode_token(name: str) -> Optional[Tuple[int, int]]:
    m = SXXEYY_RE.search(name or "")
    if m:
        return int(m.group("s")), int(m.group("e"))
    m2 = X_RE.search(name or "")
    if m2:
        return int(m2.group("s")), int(m2.group("e"))
    return None


def collect_episode_numbers(paths: List[Path]) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    seen = set()
    for p in paths:
        tok = parse_episode_token(p.name) or parse_episode_token(p.stem)
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    out.sort()
    return out


def sonarr_refresh_and_rescan(series_id: int) -> None:
    for cmd in (
        {"name": "RefreshSeries", "seriesId": series_id},
        {"name": "RescanSeries", "seriesId": series_id},
    ):
        r = _sonarr_post("/api/v3/command", cmd)
        print(f"[repair_season] POST {cmd['name']} -> {r.status_code}")
        if r.status_code >= 400:
            print(r.text)
            raise SystemExit(f"Sonarr command failed: {cmd}")
        time.sleep(SONARR_WAIT)


def sonarr_episode_search(series_id: int, episodes: List[Tuple[int, int]]) -> None:
    total = 0
    for s, e in episodes:
        er = _sonarr_get("/api/v3/episode", params={
            "seriesId": series_id,
            "seasonNumber": s,
            "episodeNumber": e,
        })
        if er.status_code >= 400:
            print(f"[repair_season] episode lookup failed S{s:02d}E{e:02d}: {er.status_code}")
            continue
        eps = er.json() or []
        ep_ids = [x["id"] for x in eps if x.get("id")]
        if not ep_ids:
            print(f"[repair_season] no episode IDs found for S{s:02d}E{e:02d}")
            continue
        cmd = {"name": "EpisodeSearch", "episodeIds": ep_ids}
        pr = _sonarr_post("/api/v3/command", cmd)
        print(f"[repair_season] POST EpisodeSearch S{s:02d}E{e:02d} -> {pr.status_code}")
        total += 1
        time.sleep(0.2)
    print(f"[repair_season] episode searches queued={total}")


def sonarr_season_search(series_id: int, season_num: int) -> None:
    cmd = {"name": "SeasonSearch", "seriesId": series_id, "seasonNumber": season_num}
    r = _sonarr_post("/api/v3/command", cmd)
    print(f"[repair_season] POST SeasonSearch -> {r.status_code}")
    if r.status_code >= 400:
        print(r.text)
        raise SystemExit("SeasonSearch failed")


def main() -> None:
    if not SHOW:
        raise SystemExit("Set REPAIR_SHOW, e.g. REPAIR_SHOW='Star Trek - Deep Space Nine'")
    if not SEASON or not SEASON.isdigit():
        raise SystemExit("Set REPAIR_SEASON to an integer, e.g. REPAIR_SEASON=3")

    season_num = int(SEASON)
    season_dir = SEASON_DIR_FMT.format(n=season_num)
    season_path = Path(LIB_ROOT_TV) / SHOW / season_dir

    print(f"[repair_season] show={SHOW!r} season={season_num} season_path={season_path}")
    print(f"[repair_season] dry_run={DRY_RUN} max_move={MAX_MOVE} quarantine_base={QUAR_BASE}")
    print(f"[repair_season] season_threshold={SEASON_SEARCH_THRESHOLD} (SeasonSearch when missing >= threshold)")

    if not season_path.exists():
        raise SystemExit(f"Season path does not exist: {season_path}")

    broken = find_broken_symlinks(season_path)
    print(f"[repair_season] broken_symlinks_found={len(broken)}")

    moved_paths: List[Path] = []
    for src in broken[:MAX_MOVE]:
        dest = quarantine_dest(src)
        if DRY_RUN:
            print(f"DRY: mv {src} -> {dest}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
            print(f"MOVED: {src} -> {dest}")
            moved_paths.append(dest)
        time.sleep(SLEEP_BETWEEN)

    if DRY_RUN:
        print("[repair_season] DRY_RUN complete (no files moved).")
        print("[repair_season] If the move list looks correct, set REPAIR_DRY_RUN=0 and rerun.")
        return

    moved = len(moved_paths)

    # ✅ If we didn't move anything *this run*, but items exist in quarantine for this season,
    # treat those as the "missing set" and still trigger Sonarr searches.
    quarantine_items = list_quarantine_items_for_season(season_path)
    if moved == 0 and quarantine_items:
        print(f"[repair_season] moved=0 but quarantine_items_for_season={len(quarantine_items)} -> will search based on quarantine set")
        moved_paths = quarantine_items  # reuse parsing logic
        moved = len(moved_paths)

    print(f"[repair_season] moved={moved}")

    # If still nothing to act on, do nothing.
    if moved == 0:
        print("[repair_season] NOOP: nothing moved and no quarantine items found; skipping Sonarr actions.")
        return

    if not SONARR_URL or not SONARR_API:
        raise SystemExit("SONARR_TV_URL / SONARR_TV_API not set (needed for refresh/rescan/search).")

    series_id = resolve_series_id(SHOW, season_path)
    if not series_id:
        raise SystemExit(f"Could not resolve Sonarr seriesId for title/folder: {SHOW}")

    print(f"[repair_season] sonarr_series_id={series_id}")

    # You asked earlier to reduce unnecessary churn — we keep refresh+rescan,
    # but you can comment these out later if you decide they're too noisy.
    sonarr_refresh_and_rescan(series_id)

    if moved >= SEASON_SEARCH_THRESHOLD:
        print(f"[repair_season] missing >= threshold ({moved} >= {SEASON_SEARCH_THRESHOLD}): SeasonSearch")
        sonarr_season_search(series_id, season_num)
    else:
        eps = collect_episode_numbers(moved_paths)
        if not eps:
            print("[repair_season] missing < threshold but couldn't parse any episode tokens from filenames.")
            print("[repair_season] Skipping search (manual interactive search recommended).")
            return
        print(f"[repair_season] missing < threshold ({moved} < {SEASON_SEARCH_THRESHOLD}): EpisodeSearch for {len(eps)} eps")
        sonarr_episode_search(series_id, eps)

    print("[repair_season] done. Now watch Sonarr queue + RDTClient, then rescan DB.")


if __name__ == "__main__":
    main()

