from __future__ import annotations
import os, re, json
from typing import Dict, Any, List
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ---- Auth / config ----
RELAY_TOKEN = os.environ.get("RELAY_TOKEN", "")

CFG: Dict[str, Dict[str,str]] = {
    # movies
    "radarr_doc": {
        "base": os.environ.get("RADARR_DOC_URL", ""),
        "key":  os.environ.get("RADARR_DOC_API", ""),
        "kind": "radarr",
    },
    "radarr_4k": {
        "base": os.environ.get("RADARR_4K_URL", ""),
        "key":  os.environ.get("RADARR_4K_API", ""),
        "kind": "radarr",
    },
    # tv
    "sonarr_tv": {
        "base": os.environ.get("SONARR_TV_URL", ""),
        "key":  os.environ.get("SONARR_TV_API", ""),
        "kind": "sonarr",
    },
    "sonarr_hayu": {
        "base": os.environ.get("SONARR_HAYU_URL", ""),
        "key":  os.environ.get("SONARR_HAYU_API", ""),
        "kind": "sonarr",
    },
}

def _pick(type_name: str) -> Dict[str,str]:
    c = CFG.get(type_name)
    if not c or not c.get("base") or not c.get("key"):
        raise ValueError(f"Unknown or unconfigured type '{type_name}'")
    return c

def _get(url: str, key: str, params: Dict[str,Any] | None=None) -> requests.Response:
    return requests.get(url, headers={"X-Api-Key": key}, params=params or {}, timeout=25)

def _post(url: str, key: str, body: Dict[str,Any]) -> requests.Response:
    return requests.post(
        url,
        headers={"X-Api-Key": key, "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=30
    )

@app.get("/health")
def health():
    missing = [t for t,c in CFG.items() if not c.get("base") or not c.get("key")]
    return jsonify(ok=True, missing=missing)

# ---- Helpers ----

# "Title S01E02" (or S1E2)
EP_RE = re.compile(r"(?P<title>.+?)\s+[Ss](?P<season>\d{1,2})[Ee](?P<episode>\d{1,3})\b")

# "Title S02" OR "Title Season 2"
SEASON_RE = re.compile(r"(?P<title>.+?)\s+(?:[Ss](?P<season>\d{1,2})\b|Season\s+(?P<season2>\d{1,2})\b)", re.IGNORECASE)

def parse_tv_auto(term: str):
    m = EP_RE.match(term or "")
    if not m:
        return None
    return {
        "title": m.group("title").strip(),
        "season": int(m.group("season")),
        "episode": int(m.group("episode")),
    }

def parse_tv_season(term: str):
    m = SEASON_RE.match(term or "")
    if not m:
        return None
    season = m.group("season") or m.group("season2")
    return {
        "title": (m.group("title") or "").strip(),
        "season": int(season),
    }

def best_series_match(items: List[Dict[str,Any]], title: str) -> Dict[str,Any] | None:
    tnorm = title.lower().strip()
    tnorm = re.sub(r"\s+\(\d{4}\)$","", tnorm)
    best = None
    for it in items or []:
        it_title = (it.get("title") or "").lower()
        it_title = re.sub(r"\s+\(\d{4}\)$","", it_title)
        if it_title == tnorm:
            return it
        if tnorm in it_title:
            best = best or it
    return best or (items[0] if items else None)

def resolve_series_id(base: str, key: str, title: str) -> tuple[int, str] | None:
    r = _get(f"{base}/api/v3/series/lookup", key, params={"term": title})
    if r.status_code >= 400:
        raise ValueError(f"lookup failed {r.status_code}: {r.text}")
    series_list = r.json() or []
    chosen = best_series_match(series_list, title)
    if not chosen or not chosen.get("id"):
        return None
    return int(chosen["id"]), (chosen.get("title") or title)

# ---- Main entrypoint ----

@app.get("/find")
def find():
    # auth
    token = request.args.get("token","")
    if RELAY_TOKEN and token != RELAY_TOKEN:
        return jsonify(error="unauthorized"), 401

    type_name = request.args.get("type","").strip()
    scope     = request.args.get("scope","").strip()
    term      = request.args.get("term","")  # used by auto/season and lookups

    try:
        cfg = _pick(type_name)
        base, key, kind = cfg["base"].rstrip("/"), cfg["key"], cfg["kind"]
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    try:
        if kind == "radarr":
            # ----- RADARR -----
            if scope in ("auto","movie"):
                if not term:
                    return jsonify(ok=False, error="term required"), 400
                r = _get(f"{base}/api/v3/movie/lookup", key, params={"term": term})
                if r.status_code >= 400:
                    return jsonify(ok=False, error=f"lookup failed {r.status_code}", detail=r.text), 400
                items = r.json() or []
                if not items:
                    return jsonify(ok=False, action="MoviesSearch", code=404, detail="no matches")
                chosen = None
                for it in items:
                    if it.get("id"):
                        chosen = it
                        break
                if not chosen:
                    return jsonify(ok=False, action="MoviesSearch", code=409,
                                   detail="movie not in Radarr library; add it first", sample=items[0]), 409

                movie_id = chosen["id"]
                cmd = {"name":"MoviesSearch", "movieIds":[movie_id]}
                pr = _post(f"{base}/api/v3/command", key, cmd)
                return jsonify(ok=200 <= pr.status_code < 300,
                               action="MoviesSearch", code=pr.status_code,
                               movieId=movie_id, title=chosen.get("title"),
                               body=cmd)

            return jsonify(ok=False, error=f"unsupported scope for radarr: {scope}"), 400

        # ----- SONARR -----
        if kind == "sonarr":
            if scope == "series":
                if not term:
                    return jsonify(ok=False, error="term required"), 400
                r = _get(f"{base}/api/v3/series/lookup", key, params={"term": term})
                if r.status_code >= 400:
                    return jsonify(ok=False, error=f"lookup failed {r.status_code}", detail=r.text), 400
                data = r.json() or []
                out = [{"title": x.get("title"), "seriesId": x.get("id")} for x in data if x.get("id")]
                return jsonify(ok=True, results=out)

            if scope == "episode":
                series_id = request.args.get("id")
                season    = request.args.get("season")
                episode   = request.args.get("episode")
                if not (series_id and season and episode):
                    return jsonify(ok=False, error="id, season, episode required"), 400
                er = _get(f"{base}/api/v3/episode", key, params={
                    "seriesId": series_id, "seasonNumber": season, "episodeNumber": episode
                })
                if er.status_code >= 400:
                    return jsonify(ok=False, error=f"episode query failed {er.status_code}", detail=er.text), 400
                eps = er.json() or []
                if not eps:
                    return jsonify(ok=False, error="no such episode"), 404
                ep_ids = [e["id"] for e in eps if e.get("id")]
                cmd = {"name": "EpisodeSearch", "episodeIds": ep_ids}
                pr = _post(f"{base}/api/v3/command", key, cmd)
                return jsonify(ok=200 <= pr.status_code < 300,
                               action="EpisodeSearch", code=pr.status_code,
                               seriesId=int(series_id), season=int(season), episode=int(episode),
                               episodeIds=ep_ids)

            # ✅ NEW: season search
            if scope == "season":
                if not term:
                    return jsonify(ok=False, error="term required"), 400
                parsed = parse_tv_season(term)
                if not parsed:
                    return jsonify(ok=False, error="could not parse 'Title Sxx' or 'Title Season N'"), 400

                resolved = resolve_series_id(base, key, parsed["title"])
                if not resolved:
                    return jsonify(ok=False, error="series not found"), 404
                series_id, series_title = resolved

                cmd = {"name": "SeasonSearch", "seriesId": series_id, "seasonNumber": parsed["season"]}
                pr = _post(f"{base}/api/v3/command", key, cmd)
                return jsonify(ok=200 <= pr.status_code < 300,
                               action="SeasonSearch", code=pr.status_code,
                               seriesId=series_id, season=parsed["season"], title=series_title,
                               body=cmd)

            if scope == "auto":
                if not term:
                    return jsonify(ok=False, error="term required"), 400
                parsed = parse_tv_auto(term)
                if not parsed:
                    return jsonify(ok=False, error="could not parse 'Title SxxEyy'"), 400

                resolved = resolve_series_id(base, key, parsed["title"])
                if not resolved:
                    return jsonify(ok=False, error="series not found"), 404
                series_id, series_title = resolved

                er = _get(f"{base}/api/v3/episode", key, params={
                    "seriesId": series_id,
                    "seasonNumber": parsed["season"],
                    "episodeNumber": parsed["episode"],
                })
                if er.status_code >= 400:
                    return jsonify(ok=False, error=f"episode query failed {er.status_code}", detail=er.text), 400
                eps = er.json() or []
                if not eps:
                    return jsonify(ok=False, error="no such episode"), 404
                ep_ids = [e["id"] for e in eps if e.get("id")]

                cmd = {"name": "EpisodeSearch", "episodeIds": ep_ids}
                pr = _post(f"{base}/api/v3/command", key, cmd)
                return jsonify(ok=200 <= pr.status_code < 300,
                               action="EpisodeSearch", code=pr.status_code,
                               seriesId=series_id, season=parsed["season"], episode=parsed["episode"],
                               episodeIds=ep_ids, title=series_title)

            return jsonify(ok=False, error=f"unsupported scope for sonarr: {scope}"), 400

        return jsonify(ok=False, error="unreachable"), 500

    except requests.RequestException as e:
        return jsonify(ok=False, error="request failed", detail=str(e)), 502
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5050")), debug=False)

