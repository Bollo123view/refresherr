from flask import Flask, request, jsonify
import os, requests, urllib.parse, logging, re

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

SECRET = os.getenv("RELAY_TOKEN", "")

INSTANCES = {
    "sonarr_tv":   {"url": os.getenv("SONARR_TV_URL"),   "api": os.getenv("SONARR_TV_API"),   "kind": "sonarr"},
    "sonarr_hayu": {"url": os.getenv("SONARR_HAYU_URL"), "api": os.getenv("SONARR_HAYU_API"), "kind": "sonarr"},
    "radarr_doc":  {"url": os.getenv("RADARR_DOC_URL"),  "api": os.getenv("RADARR_DOC_API"),  "kind": "radarr"},
    "radarr_4k":   {"url": os.getenv("RADARR_4K_URL"),   "api": os.getenv("RADARR_4K_API"),   "kind": "radarr"},
}

def bad(msg, code=400):
    app.logger.error(msg)
    return jsonify({"error": msg}), code

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})

@app.get("/find")
def find():
    token = request.args.get("token", "")
    if SECRET and token != SECRET:
        return bad("unauthorized", 403)

    mtype = (request.args.get("type") or "").strip()
    term  = (request.args.get("term") or "").strip()
    if not mtype or not term:
        return bad("missing type or term")

    inst = INSTANCES.get(mtype)
    if not inst:
        return bad("invalid type")
    base = (inst.get("url") or "").rstrip("/")
    api  = (inst.get("api") or "")
    kind = (inst.get("kind") or "")
    if not base or not api or not kind:
        return bad("instance misconfigured", 500)

    headers = {"X-Api-Key": api, "Content-Type": "application/json"}
    q = urllib.parse.quote(term)

    try:
        if kind == "sonarr":
            r = requests.get(f"{base}/api/v3/series", headers=headers, timeout=10)
            r.raise_for_status()
            lib = r.json()
            nterm = norm(term)
            cand = [s for s in lib if nterm in norm(s.get("title") or s.get("sortTitle"))]
            series = None
            if cand:
                cand.sort(key=lambda s: (not norm(s.get("title","")).startswith(nterm), -len(s.get("title",""))))
                series = cand[0]
            else:
                r = requests.get(f"{base}/api/v3/series/lookup?term={q}", headers=headers, timeout=10)
                r.raise_for_status()
                lookup = r.json()
                if lookup:
                    tvdb = lookup[0].get("tvdbId")
                    if tvdb:
                        for s in lib:
                            if s.get("tvdbId") == tvdb:
                                series = s
                                break
            if not series:
                return bad(f"series '{term}' not in library (add to Sonarr first)", 404)
            series_id = series["id"]
            r = requests.post(f"{base}/api/v3/command", headers=headers,
                              json={"name": "SeriesSearch", "seriesId": series_id}, timeout=10)
            r.raise_for_status()
            return jsonify({"status": f"SeriesSearch started for '{term}'", "seriesId": series_id})

        r = requests.get(f"{base}/api/v3/movie", headers=headers, timeout=10)
        r.raise_for_status()
        movies = r.json()
        m = re.search(r"\((\d{4})\)$", term)
        year = int(m.group(1)) if m else None
        title_only = term if not year else term[:term.rfind("(")].strip()
        nm = norm(title_only)
        cand = []
        for mv in movies:
            t = mv.get("title",""); y = mv.get("year")
            if nm in norm(t):
                score = 0
                if year and y == year: score -= 10
                score -= len(t)
                cand.append((score, mv))
        movie = cand and sorted(cand, key=lambda x:x[0])[0][1] or None
        if not movie:
            r = requests.get(f"{base}/api/v3/movie/lookup?term={q}", headers=headers, timeout=10)
            r.raise_for_status()
            lookup = r.json()
            if lookup:
                tmdb = lookup[0].get("tmdbId"); imdb = lookup[0].get("imdbId")
                for mv in movies:
                    if (tmdb and mv.get("tmdbId")==tmdb) or (imdb and mv.get("imdbId")==imdb):
                        movie = mv; break
        if not movie:
            return bad(f"movie '{term}' not in library (add to Radarr first)", 404)
        movie_id = movie["id"]
        r = requests.post(f"{base}/api/v3/command", headers=headers,
                          json={"name": "MoviesSearch", "movieIds": [movie_id]}, timeout=10)
        r.raise_for_status()
        return jsonify({"status": f"MoviesSearch started for '{term}'", "movieId": movie_id})
    except requests.RequestException as e:
        return bad(f"upstream error: {e}", 502)
