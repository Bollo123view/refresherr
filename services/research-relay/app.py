#!/usr/bin/env python3
"""
Research Relay - smart 'auto' finder for Sonarr/Radarr.

GET /find?token=...&type=<sonarr_tv|sonarr_hayu|radarr_doc|radarr_4k>&scope=<auto|series|season|episodes|movie>
  &term=<series or movie title>
  [&season=1]
  [&episodes=1,2,3]

Env expected (examples):
  RELAY_TOKEN
  SONARR_TV_URL / SONARR_TV_API
  SONARR_HAYU_URL / SONARR_HAYU_API
  RADARR_DOC_URL / RADARR_DOC_API
  RADARR_4K_URL / RADARR_4K_API
"""

import os, time, json, typing as t
from flask import Flask, request, jsonify
import requests
from functools import lru_cache

app = Flask(__name__)

RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")
MIN_INTERVAL_SEC = int(os.environ.get("RELAY_MIN_INTERVAL_SEC", "5"))
_last_sent = {}  # per-instance pacing

def _pace(key: str) -> bool:
    now = time.time()
    last = _last_sent.get(key, 0.0)
    if now - last >= MIN_INTERVAL_SEC:
        _last_sent[key] = now
        return True
    return False

class ArrClient(t.TypedDict):
    base: str
    key: str
    kind: str  # 'sonarr' or 'radarr'

INSTANCES: t.Dict[str, ArrClient] = {
    "sonarr_tv":   {"base": os.environ.get("SONARR_TV_URL", ""),   "key": os.environ.get("SONARR_TV_API", ""),   "kind": "sonarr"},
    "sonarr_hayu": {"base": os.environ.get("SONARR_HAYU_URL", ""),  "key": os.environ.get("SONARR_HAYU_API", ""), "kind": "sonarr"},
    "radarr_doc":  {"base": os.environ.get("RADARR_DOC_URL", ""),   "key": os.environ.get("RADARR_DOC_API", ""),  "kind": "radarr"},
    "radarr_4k":   {"base": os.environ.get("RADARR_4K_URL", ""),    "key": os.environ.get("RADARR_4K_API", ""),   "kind": "radarr"},
}

def _headers(key: str):
    return {"X-Api-Key": key, "Content-Type": "application/json"}

def _resp(data=None, status=200):
    return jsonify(data or {}), status

# ---------------------- Sonarr helpers ----------------------

def sonarr_lookup_series(base: str, key: str, term: str):
    # Try direct series list (faster, stable path matching), then name lookup
    r = requests.get(f"{base}/api/v3/series", headers=_headers(key), timeout=30)
    r.raise_for_status()
    all_series = r.json()
    # Name match (case-insensitive contains)
    term_l = term.lower()
    ranked = sorted(
        [s for s in all_series if term_l in (s.get("title") or "").lower()],
        key=lambda s: 0 if (s.get("title") or "").lower() == term_l else 1
    )
    if ranked:
        return ranked[0]
    # fallback to lookup endpoint
    r = requests.get(f"{base}/api/v3/series/lookup", params={"term": term}, headers=_headers(key), timeout=30)
    r.raise_for_status()
    arr = r.json()
    return arr[0] if arr else None

def sonarr_missingness(base: str, key: str, series_id: int):
    r = requests.get(f"{base}/api/v3/episode", params={"seriesId": series_id}, headers=_headers(key), timeout=30)
    r.raise_for_status()
    eps = r.json()
    monitored = [e for e in eps if e.get("monitored")]
    missing = [e for e in monitored if not e.get("hasFile")]
    seasons = {}
    for e in monitored:
        sn = e.get("seasonNumber")
        d = seasons.setdefault(sn, {"tot":0, "miss":0, "ids_missing": []})
        d["tot"] += 1
        if not e.get("hasFile"):
            d["miss"] += 1
            d["ids_missing"].append(e["id"])
    return {
        "monitored": len(monitored),
        "missing": len(missing),
        "seasons": seasons,
        "missing_ids": [e["id"] for e in missing]
    }

def sonarr_command(base: str, key: str, payload: dict):
    r = requests.post(f"{base}/api/v3/command", headers=_headers(key), data=json.dumps(payload), timeout=30)
    return r

# ---------------------- Radarr helpers ----------------------

def radarr_lookup_movie(base: str, key: str, term: str):
    # Prefer library match first
    r = requests.get(f"{base}/api/v3/movie", headers=_headers(key), timeout=30)
    r.raise_for_status()
    movies = r.json()
    term_l = term.lower()
    ranked = sorted(
        [m for m in movies if term_l in (m.get("title") or "").lower()],
        key=lambda m: 0 if (m.get("title") or "").lower() == term_l else 1
    )
    if ranked:
        return ranked[0]
    # Fallback to lookup
    r = requests.get(f"{base}/api/v3/movie/lookup", params={"term": term}, headers=_headers(key), timeout=30)
    r.raise_for_status()
    arr = r.json()
    return arr[0] if arr else None

def radarr_command(base: str, key: str, payload: dict):
    r = requests.post(f"{base}/api/v3/command", headers=_headers(key), data=json.dumps(payload), timeout=30)
    return r

# ---------------------- API ----------------------

@app.route("/find")
def find():
    token = request.args.get("token", "")
    if not RELAY_TOKEN or token != RELAY_TOKEN:
        return _resp({"error":"unauthorized"}, 401)
    inst_key = request.args.get("type")
    scope = request.args.get("scope", "auto")
    term = request.args.get("term", "")
    season = request.args.get("season")
    episodes = request.args.get("episodes")

    if inst_key not in INSTANCES:
        return _resp({"error":"unknown type"}, 400)
    inst = INSTANCES[inst_key]
    base, key, kind = inst["base"], inst["key"], inst["kind"]
    if not base or not key:
        return _resp({"error":"instance not configured"}, 500)

    # rate-limit pacing
    if not _pace(inst_key):
        return _resp({"status":"paced"}, 202)

    try:
        if kind == "sonarr":
            if scope == "auto":
                if not term:
                    return _resp({"error":"term required"}, 400)
                s = sonarr_lookup_series(base, key, term)
                if not s: return _resp({"error":"series not found"}, 404)
                series_id = s["id"]
                miss = sonarr_missingness(base, key, series_id)
                if miss["monitored"] > 0 and miss["missing"]/miss["monitored"] >= 0.5:
                    payload = {"name":"SeriesSearch","seriesId":series_id}
                    r = sonarr_command(base, key, payload)
                    return _resp({"action":"SeriesSearch","seriesId":series_id,"code":r.status_code})
                # fully-missing season?
                full = [sn for sn, v in miss["seasons"].items() if v["tot"]>0 and v["miss"]==v["tot"] and sn != 0]
                if full:
                    sn = sorted(full)[0]
                    payload = {"name":"SeasonSearch","seriesId":series_id,"seasonNumber":sn}
                    r = sonarr_command(base, key, payload)
                    return _resp({"action":"SeasonSearch","seriesId":series_id,"season":sn,"code":r.status_code})
                # else episodes batched up to 20 ids
                ids = miss["missing_ids"][:20]
                if ids:
                    payload = {"name":"EpisodeSearch","episodeIds":ids}
                    r = sonarr_command(base, key, payload)
                    return _resp({"action":"EpisodeSearch","episodeIds":ids,"code":r.status_code})
                return _resp({"action":"noop","reason":"nothing missing"})
            elif scope == "series":
                series_id = request.args.get("seriesId", type=int)
                if not series_id and term:
                    s = sonarr_lookup_series(base, key, term)
                    series_id = s["id"] if s else None
                if not series_id: return _resp({"error":"seriesId/term required"},400)
                r = sonarr_command(base, key, {"name":"SeriesSearch","seriesId":series_id})
                return _resp({"action":"SeriesSearch","seriesId":series_id,"code":r.status_code})
            elif scope == "season":
                series_id = request.args.get("seriesId", type=int)
                sn = request.args.get("season", type=int) or 1
                if not series_id and term:
                    s = sonarr_lookup_series(base, key, term); series_id = s["id"] if s else None
                r = sonarr_command(base, key, {"name":"SeasonSearch","seriesId":series_id,"seasonNumber":sn})
                return _resp({"action":"SeasonSearch","seriesId":series_id,"season":sn,"code":r.status_code})
            elif scope == "episodes":
                ids = [int(x) for x in (episodes or "").split(",") if x.strip().isdigit()]
                if not ids: return _resp({"error":"episodeIds required"},400)
                r = sonarr_command(base, key, {"name":"EpisodeSearch","episodeIds":ids})
                return _resp({"action":"EpisodeSearch","episodeIds":ids,"code":r.status_code})
            else:
                return _resp({"error":"bad scope"},400)

        else:  # radarr
            if scope == "auto" or scope == "movie":
                if not term: return _resp({"error":"term required"},400)
                m = radarr_lookup_movie(base, key, term)
                if not m: return _resp({"error":"movie not found"},404)
                mid = m["id"]
                r = radarr_command(base, key, {"name":"MoviesSearch","movieIds":[mid]})
                return _resp({"action":"MoviesSearch","movieId":mid,"code":r.status_code})
            else:
                return _resp({"error":"radarr supports 'movie' or 'auto' only"},400)

    except requests.HTTPError as he:
        return _resp({"error":"http", "detail":str(he)}, 502)
    except Exception as e:
        return _resp({"error":"exception", "detail":str(e)}, 500)

@app.route("/health")
def health():
    return _resp({"ok":True})
