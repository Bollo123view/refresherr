from __future__ import annotations
import os, sqlite3, math, time, re, sys
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, Blueprint
)
import requests

# Import central config module
# Dynamically add paths based on environment
_app_base = os.environ.get('APP_BASE', '/app')
_refresher_path = os.path.join(_app_base, 'refresher') if os.path.exists(os.path.join(_app_base, 'refresher')) else '/app/refresher'
if _app_base not in sys.path:
    sys.path.insert(0, _app_base)
if _refresher_path not in sys.path:
    sys.path.insert(0, _refresher_path)

try:
    from config import load_config, get_config, to_dict as config_to_dict, route_for_path
    CONFIG_MODULE_AVAILABLE = True
except ImportError:
    CONFIG_MODULE_AVAILABLE = False
    print("Warning: Central config module not available, using legacy config")

# Import orchestrator and repair modules if available
try:
    from refresher.core import orchestrator
    from refresher.core import repair_runner
    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    ORCHESTRATOR_AVAILABLE = False
    print("Warning: Orchestrator module not available")

# ---------- Config ----------
DATA_DIR      = os.environ.get("DATA_DIR", "/data")
DB_PATH       = os.path.join(DATA_DIR, "symlinks.db")
RELAY_BASE    = os.environ.get("RELAY_BASE", "")   # e.g. http://research-relay:5050/find
RELAY_TOKEN   = os.environ.get("RELAY_TOKEN", "")
SYMLINK_ROOT  = os.environ.get("SYMLINK_ROOT", "/opt/media/jelly")

# Optional routing by symlink prefix → instance
INSTANCE_BY_PREFIX = [
    ("/opt/media/jelly/4k",     "radarr_movie"),
    ("/opt/media/jelly/movies", "radarr_movie"),
    ("/opt/media/jelly/tv",     "sonarr_tv"),
    ("/opt/media/jelly/hayu",   "sonarr_hayu"),
]

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "refresherr-demo-secret")

# ===== Build/Rev visibility ==================================================
REV = os.environ.get("GIT_REV", "local-dev")

@app.after_request
def _stamp_rev(resp):
    # Helpful header to prove which build is running
    resp.headers["X-Refresherr-Rev"] = REV
    # Make HTML less sticky while iterating UI
    ct = resp.headers.get("Content-Type", "")
    if "text/html" in ct:
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp

@app.context_processor
def inject_helpers():
    return dict(sizeof_fmt=sizeof_fmt, build_rev=REV)

# ===== DB / Helpers ==========================================================
def db():
    p = DB_PATH
    # Auto-create database if it doesn't exist
    if not os.path.exists(p):
        # Ensure data directory exists
        os.makedirs(os.path.dirname(p), exist_ok=True)
        # Initialize database schema
        try:
            from refresher.core.db import initialize_schema
            conn = sqlite3.connect(p, timeout=5, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            initialize_schema(conn)
            print(f"Database initialized at {p}")
        except ImportError:
            # Fallback: create empty database if core module unavailable
            conn = sqlite3.connect(p, timeout=5, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            print(f"Database created at {p} (schema initialization unavailable)")
    else:
        conn = sqlite3.connect(p, timeout=5, check_same_thread=False)
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn

def sizeof_fmt(num: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"

def pick_instance_from_path(p: str) -> str | None:
    for prefix, instance in INSTANCE_BY_PREFIX:
        if p.startswith(prefix):
            return instance
    return None

# ===== Health / DBcheck ======================================================
@app.route("/health")
def health():
    try:
        c = db().cursor()
        c.execute("SELECT 1")
        return jsonify(ok=True)
    except Exception as e:
        # During startup, database might be initializing - be more lenient
        error_msg = str(e)
        # If it's just a missing table during initialization, that's recoverable
        if "no such table" in error_msg.lower():
            return jsonify(ok=True, warning="Database initializing"), 200
        return jsonify(ok=False, error=error_msg), 500

@app.route("/dbcheck")
def dbcheck():
    try:
        conn = db(); c = conn.cursor()
        out = {}
        for name in ("movies","movie_files","series","episode_files","symlinks","actions"):
            try:
                c.execute(f"SELECT COUNT(*) FROM {name}")
                out[name] = c.fetchone()[0]
            except Exception as ex:
                out[name] = f"err: {ex}"
        try:
            cols = conn.execute("PRAGMA table_info(symlinks)").fetchall()
            names = {r["name"] for r in cols}
            out["symlinks_has_last_status"]  = "last_status"  in names
            out["symlinks_has_status"]       = "status"       in names
            out["symlinks_has_last_seen_ts"] = "last_seen_ts" in names
        except Exception as ex:
            out["pragma_err"] = str(ex)
        return out
    except Exception as e:
        return {"error": str(e)}, 500

# ===== Counters ============================================================== 
def query_counters(cur):
    cur.execute("SELECT COUNT(*) FROM movie_files WHERE symlink_path IS NOT NULL")
    movies_linked = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM movie_files")
    movies_total = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM episode_files WHERE symlink_path IS NOT NULL")
    eps_linked = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM episode_files")
    eps_total = cur.fetchone()[0] or 0
    try:
        cur.execute("SELECT COUNT(*) FROM symlinks WHERE COALESCE(last_status, status)='broken'")
        broken_count = cur.fetchone()[0] or 0
    except Exception:
        broken_count = 0
    mov_pct = (movies_linked / movies_total * 100.0) if movies_total else 0.0
    eps_pct = (eps_linked / eps_total * 100.0) if eps_total else 0.0
    return movies_linked, movies_total, mov_pct, eps_linked, eps_total, eps_pct, broken_count

# ===== Parsing helpers (TV/movie normalisation) ==============================
TV_SE_PATTERN = re.compile(r"[Ss](\d{1,2})[ ._-]*[Ee](\d{1,3})")
YEAR_PAREN_PATTERN = re.compile(r"\((\d{4})\)$")

def parse_tv_from_path(p: str):
    """Return (series_title, season_num, episode_num) from a typical TV path."""
    parts = p.strip("/").split("/")
    series_title = ""
    season_num = None
    episode_num = None

    try:
        if len(parts) >= 3 and parts[-2].lower().startswith(("season ", "series ")):
            series_title = parts[-3]
            try:
                # Season 5 → 5
                import re as _re
                season_num = int(_re.sub(r"\D", "", parts[-2]))
            except Exception:
                season_num = None
        else:
            series_title = parts[-2] if len(parts) >= 2 else ""
    except Exception:
        series_title = ""

    fname = os.path.basename(p)
    m = TV_SE_PATTERN.search(fname)
    if m:
        try:  season_num = season_num or int(m.group(1))
        except Exception: pass
        try:  episode_num = int(m.group(2))
        except Exception: pass

    return series_title.strip(), season_num, episode_num

def parse_year_from_title(title: str | None):
    if not title:
        return None
    m = YEAR_PAREN_PATTERN.search(title)
    if m:
        try:
            y = int(m.group(1))
            if 1900 <= y <= 2100:
                return y
        except Exception:
            return None
    return None

# ===== Builders shared by HTML + API ========================================
def build_broken_items(conn):
    rows = conn.execute("""
        SELECT
            path,
            last_target,
            COALESCE(last_status, status) AS status,
            COALESCE(last_seen_ts, first_seen_ts, 0) AS seen_ts
        FROM symlinks
        WHERE COALESCE(last_status, status)='broken'
        ORDER BY seen_ts DESC, rowid DESC
        LIMIT 200
    """).fetchall()
    items = []
    for r in rows:
        sp = r["path"]
        term = os.path.basename(os.path.dirname(sp))
        items.append({
            "path": sp,
            "last_target": r["last_target"],
            "term": term,
            "status": r["status"],
            # hints for normaliser:
            "display_title": term,
            "library_path": sp,
            "target_path": r["last_target"],
            "can_repair": True,  # broken → actionable
        })
    return items

def build_movie_items(conn, q: str):
    rows = conn.execute("""
        SELECT mf.id, mf.instance, mf.quality, mf.resolution, mf.size_bytes, mf.symlink_path
        FROM movie_files mf
        WHERE mf.symlink_path IS NOT NULL
        ORDER BY mf.id DESC
    """).fetchall()
    ql = q.strip().lower()
    items = []
    for r in rows:
        sp = r["symlink_path"] or ""
        title = os.path.basename(os.path.dirname(sp)) if sp else ""
        if ql and ql not in title.lower():
            continue
        items.append({
            "id": r["id"],
            "instance": r["instance"],
            "title": title,
            "movie_title": title,
            "quality": r["quality"],
            "resolution": r["resolution"],
            "size": r["size_bytes"],
            "symlink_path": sp,
            "display_title": title,
            "library_path": sp,
            "status": "ok",
        })
    return items

def build_episode_items(conn, q: str):
    rows = conn.execute("""
        SELECT ef.id, ef.instance, ef.season_number, ef.quality, ef.resolution, ef.size_bytes, ef.symlink_path,
               ef.sonarr_series_id, s.title as series_title
        FROM episode_files ef
        LEFT JOIN series s ON s.sonarr_id = ef.sonarr_series_id AND s.instance = ef.instance
        WHERE ef.symlink_path IS NOT NULL
        ORDER BY ef.id DESC
    """).fetchall()
    ql = q.strip().lower()
    items = []
    for r in rows:
        sp = r["symlink_path"] or ""
        epname = os.path.basename(sp) if sp else ""
        title = (r["series_title"] or "")
        if ql and (ql not in title.lower() and ql not in epname.lower()):
            continue
        items.append({
            "id": r["id"],
            "instance": r["instance"],
            "series_title": title,
            "episode_name": epname,
            "season": r["season_number"],
            "quality": r["quality"],
            "resolution": r["resolution"],
            "size": r["size_bytes"],
            "symlink_path": sp,
            "display_title": title or epname,
            "library_path": sp,
            "status": "ok",
        })
    return items

# ===== Normaliser for UI + API ==============================================
def _unify_item(it):
    title = (
        it.get("series_title")
        or it.get("movie_title")
        or it.get("display_title")
        or it.get("title")
        or it.get("name")
        or it.get("filename")
    )

    lib_path   = (it.get("library_path") or it.get("symlink_path") or it.get("path") or "") or ""
    target_path= it.get("target_path") or it.get("last_target")

    # Determine kind
    kind   = it.get("kind")
    season = it.get("season")
    episode= it.get("episode")

    if not kind:
        lp = lib_path.lower()
        if "/tv/" in lp or "/hayu/" in lp or TV_SE_PATTERN.search(os.path.basename(lib_path or "")):
            kind = "episode"
        else:
            kind = "movie"

    # For episodes, parse series/season/episode from path
    if kind == "episode":
        series_title, s_num, e_num = parse_tv_from_path(lib_path)
        season = season if season is not None else s_num
        episode = episode if episode is not None else e_num
        if title and title.lower().startswith("season "):
            title = series_title or title
        elif not title:
            title = series_title

    # Infer movie year if present in title
    year = it.get("year")
    if year is None and kind == "movie":
        year = parse_year_from_title(title)

    status = it.get("status", "ok")
    can_repair = bool(it.get("can_repair", status == "broken"))

    return {
        "kind": kind,
        "title": title,
        "season": season,
        "episode": episode,
        "year": year,
        "status": status,
        "reason": it.get("reason"),
        "can_repair": can_repair,
        "ids": {"jellyfin": it.get("jellyfin_id"), "tmdb": it.get("tmdb_id")},
        "paths": {"library": lib_path, "target": target_path},
        # passthrough
        "quality": it.get("quality"),
        "resolution": it.get("resolution"),
        "size": it.get("size"),
        "instance": it.get("instance"),
    }

# ===== Pagination ============================================================
def paginate(q, page, per_page=50):
    total = len(q)
    start = (page-1)*per_page
    end = start + per_page
    items = q[start:end]
    pages = math.ceil(total/per_page) if per_page else 1
    return items, total, pages

# ===== HTML Routes ===========================================================
@app.route("/")
def index():
    conn = db()
    cur = conn.cursor()
    movies_linked, movies_total, mov_pct, eps_linked, eps_total, eps_pct, broken_count = query_counters(cur)
    return render_template(
        "index.html",
        movies_linked=movies_linked, movies_total=movies_total, mov_pct=mov_pct,
        eps_linked=eps_linked, eps_total=eps_total, eps_pct=eps_pct,
        broken=broken_count,
        relay_ok=bool(RELAY_BASE and RELAY_TOKEN)
    )

@app.get("/broken")
def broken():
    conn = db(); cur = conn.cursor()
    counters = query_counters(cur)
    raw_items = build_broken_items(conn)
    items = [_unify_item(x) for x in raw_items]
    return render_template(
        "broken.html",
        items=items,
        movies_linked=counters[0], movies_total=counters[1], mov_pct=counters[2],
        eps_linked=counters[3], eps_total=counters[4], eps_pct=counters[5],
        broken=counters[6],
        relay_ok=bool(RELAY_BASE and RELAY_TOKEN)
    )

@app.route("/movies")
def movies():
    conn = db()
    q = request.args.get("q","").strip()
    raw_items = build_movie_items(conn, q)
    items = [_unify_item(x) for x in raw_items]
    page = int(request.args.get("page", "1") or "1")
    page_items, total, pages = paginate(items, page, per_page=50)
    return render_template("movies.html", items=page_items, total=total, page=page, pages=pages, q=q)

@app.route("/episodes")
def episodes():
    conn = db()
    q = request.args.get("q","").strip()
    raw_items = build_episode_items(conn, q)
    items = [_unify_item(x) for x in raw_items]
    page = int(request.args.get("page", "1") or "1")
    page_items, total, pages = paginate(items, page, per_page=50)
    return render_template("episodes.html", items=page_items, total=total, page=page, pages=pages, q=q)

# ===== Auto action ===========================================================
@app.post("/action/auto")
def action_auto():
    if not (RELAY_BASE and RELAY_TOKEN):
        flash("Relay not configured", "danger")
        return redirect(request.referrer or url_for("index"))

    term = (request.form.get("term") or "").strip()
    typ  = (request.form.get("type") or "").strip()
    path = (request.form.get("path") or "").strip()

    if not term and path:
        try:
            term = os.path.basename(os.path.dirname(path)) or ""
        except Exception:
            term = ""

    if not (term and path):
        flash("Missing term or path", "danger")
        return redirect(request.referrer or url_for("index"))

    if not path.startswith(SYMLINK_ROOT.rstrip("/") + "/"):
        flash("Refusing to modify a path outside the symlink root.", "danger")
        return redirect(request.referrer or url_for("index"))

    if not typ:
        inst = pick_instance_from_path(path)
        if inst is None:
            inst = "sonarr_tv" if ("/tv/" in path or "/hayu/" in path) else "radarr_movie"
    else:
        inst = typ

    conn = db(); cur = conn.cursor(); now = int(time.time())

    # Unlink safely
    try:
        if os.path.islink(path):
            os.unlink(path)
        else:
            flash("Not a symlink; leaving file untouched.", "warning")
    except Exception as e:
        flash(f"Unlink failed: {e}", "warning")

    # Mark repairing
    try:
        cur.execute("""
            UPDATE symlinks
               SET last_status='repairing',
                   last_target=NULL,
                   last_seen_ts=?
             WHERE path=?
        """, (now, path))
        conn.commit()
    except Exception as e:
        flash(f"DB update failed: {e}", "danger")

    # Ensure actions + insert
    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS actions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_ts INTEGER DEFAULT (strftime('%s','now')),
          source TEXT,
          instance TEXT,
          subject_type TEXT,
          subject_id INTEGER,
          subject_title TEXT,
          scope TEXT,
          status TEXT DEFAULT 'enqueued',
          last_error TEXT
        )
        """)
        subject_type = "series" if inst.startswith("sonarr") else "movie"
        cur.execute("""
            INSERT INTO actions(source, instance, subject_type, subject_id, subject_title, scope, status)
            VALUES(?,?,?,?,?,?,?)
        """, ("dashboard", inst, subject_type, None, term, "auto", "enqueued"))
        conn.commit()
    except Exception as e:
        flash(f"Action log insert failed: {e}", "warning")

    # Relay call
    try:
        resp = requests.get(RELAY_BASE, params={
            "token": RELAY_TOKEN, "type": inst, "scope": "auto", "term": term
        }, timeout=20)
        ok = 200 <= resp.status_code < 300
        msg = f"AUTO {inst} '{term}': {resp.status_code} {resp.text[:160]}"
        flash(msg, "success" if ok else "warning")
        try:
            cur.execute("UPDATE actions SET status=? WHERE id=(SELECT MAX(id) FROM actions)", ("ok" if ok else "failed",))
            if not ok:
                cur.execute("UPDATE actions SET last_error=? WHERE id=(SELECT MAX(id) FROM actions)", (resp.text[:300],))
            conn.commit()
        except Exception:
            pass
    except Exception as e:
        flash(f"AUTO failed: {e}", "danger")
        try:
            cur.execute("UPDATE actions SET status=?, last_error=? WHERE id=(SELECT MAX(id) FROM actions)", ("failed", str(e)[:300]))
            conn.commit()
        except Exception:
            pass

    return redirect(request.referrer or url_for("index"))

# ===== API ===================================================================
api = Blueprint("api", __name__, url_prefix="/api")

@api.get("/broken")
def api_broken():
    conn = db()
    items = [_unify_item(x) | {"status": "broken"} for x in build_broken_items(conn)]
    return jsonify(items)

@api.get("/movies")
def api_movies():
    conn = db()
    items = [_unify_item(x) | {"kind": "movie"} for x in build_movie_items(conn, q="")]
    return jsonify(items)

@api.get("/episodes")
def api_episodes():
    conn = db()
    items = [_unify_item(x) | {"kind": "episode"} for x in build_episode_items(conn, q="")]
    return jsonify(items)

@api.get("/config")
def api_config():
    """
    Expose current configuration for UI discovery and debugging.
    Returns the configuration loaded from YAML/env with sensitive data masked.
    """
    if CONFIG_MODULE_AVAILABLE:
        try:
            config = get_config()
            return jsonify(config_to_dict(config))
        except Exception as e:
            return jsonify({"error": f"Failed to load config: {e}"}), 500
    else:
        # Fallback to basic config info
        return jsonify({
            "scan": {
                "roots": [SYMLINK_ROOT] if SYMLINK_ROOT else [],
                "interval": int(os.environ.get("SCAN_INTERVAL", "300"))
            },
            "relay": {
                "base_url": RELAY_BASE,
                "token_set": bool(RELAY_TOKEN)
            },
            "database": {
                "path": DB_PATH,
                "data_dir": DATA_DIR
            },
            "routing": [{"prefix": p, "type": t} for p, t in INSTANCE_BY_PREFIX],
            "dryrun": os.environ.get("DRYRUN", "true").lower() == "true",
            "note": "Central config module not available, showing env-based config"
        })

@api.get("/routes")
def api_routes():
    """
    Expose routing/mapping configuration for UI visibility and troubleshooting.
    Shows how paths are mapped and routed to different instances.
    """
    if CONFIG_MODULE_AVAILABLE:
        try:
            config = get_config()
            return jsonify({
                "routing": [
                    {"prefix": r.prefix, "type": r.type}
                    for r in config.routing
                ],
                "path_mappings": [
                    {
                        "container_path": m.container_path,
                        "logical_path": m.logical_path,
                        "description": m.description
                    }
                    for m in config.path_mappings
                ],
                "examples": [
                    {
                        "path": r.prefix + "/Example Show/Season 1/episode.mkv",
                        "routes_to": r.type,
                        "description": f"Content under {r.prefix} routes to {r.type}"
                    }
                    for r in config.routing[:3]  # Show first 3 as examples
                ]
            })
        except Exception as e:
            return jsonify({"error": f"Failed to load routing config: {e}"}), 500
    else:
        # Fallback routing info
        return jsonify({
            "routing": [{"prefix": p, "type": t} for p, t in INSTANCE_BY_PREFIX],
            "path_mappings": [],
            "examples": [
                {
                    "path": p + "/Example/file.mkv",
                    "routes_to": t,
                    "description": f"Content under {p} routes to {t}"
                }
                for p, t in INSTANCE_BY_PREFIX[:3]
            ],
            "note": "Central config module not available, showing legacy routing"
        })

@api.get("/stats")
def api_stats():
    """
    Expose symlink statistics for dashboard display.
    """
    try:
        conn = db()
        cur = conn.cursor()
        movies_linked, movies_total, mov_pct, eps_linked, eps_total, eps_pct, broken_count = query_counters(cur)
        
        # Get additional stats
        cur.execute("SELECT COUNT(*) FROM symlinks")
        total_symlinks = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM symlinks WHERE COALESCE(last_status, status)='ok'")
        ok_symlinks = cur.fetchone()[0] or 0
        
        return jsonify({
            "movies": {
                "linked": movies_linked,
                "total": movies_total,
                "percentage": round(mov_pct, 1)
            },
            "episodes": {
                "linked": eps_linked,
                "total": eps_total,
                "percentage": round(eps_pct, 1)
            },
            "symlinks": {
                "total": total_symlinks,
                "ok": ok_symlinks,
                "broken": broken_count,
                "percentage_healthy": round((ok_symlinks / total_symlinks * 100.0) if total_symlinks else 0.0, 1)
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.get("/manifest")
def api_manifest():
    """
    Get the dry run manifest showing what actions would be performed.
    This endpoint returns a detailed preview of all repair actions.
    """
    try:
        # Import scanner using existing path configuration
        sys.path.insert(0, _app_base)
        sys.path.insert(0, _refresher_path)
        
        from refresher.core.scanner import scan_once
        from refresher.config import load_config
        
        # Perform a scan to get current manifest
        config_path = os.environ.get("CONFIG_FILE", "/config/config.yaml")
        try:
            config = load_config(config_path)
            result = scan_once(config, dryrun=True)
        except Exception:
            # Fallback to path-based loading
            result = scan_once(config_path, dryrun=True)
        
        summary = result.get("summary", {})
        
        return jsonify({
            "dryrun": summary.get("dryrun", True),
            "broken_count": summary.get("broken_count", 0),
            "examined": summary.get("examined", 0),
            "manifest": summary.get("manifest", []),
            "manifest_summary": summary.get("manifest_summary", {}),
            "timestamp": time.time()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.post("/config/dryrun")
def api_set_dryrun():
    """
    Toggle dry run mode on/off.
    Expects JSON body: {"dryrun": true/false}
    
    Note: This updates the environment variable for the current process.
    For persistent changes across restarts, update .env file manually.
    """
    try:
        data = request.get_json()
        if data is None or "dryrun" not in data:
            return jsonify({"error": "Missing 'dryrun' field in request body"}), 400
        
        dryrun = bool(data["dryrun"])
        
        # Update environment variable for current process
        os.environ["DRYRUN"] = "true" if dryrun else "false"
        
        # If config module is available, reload config to pick up the change
        if CONFIG_MODULE_AVAILABLE:
            try:
                from config import get_config
                config = get_config(reload=True)
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "dryrun": dryrun,
            "message": f"Dry run mode {'enabled' if dryrun else 'disabled'}. Note: This change is not persistent across restarts. Update .env for persistence."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.post("/orchestrator/toggle")
def api_orchestrator_toggle():
    """
    Toggle the auto-repair orchestrator on or off.
    Expects JSON body: {"enabled": true/false}
    """
    if not ORCHESTRATOR_AVAILABLE:
        return jsonify({"error": "Orchestrator module not available"}), 503
    
    try:
        data = request.get_json()
        if data is None or "enabled" not in data:
            return jsonify({"error": "Missing 'enabled' field in request body"}), 400
        
        enabled = bool(data["enabled"])
        state = orchestrator.set_orchestrator_enabled(enabled)
        
        return jsonify({
            "success": True,
            "state": state,
            "message": f"Auto-repair orchestrator {'enabled' if enabled else 'disabled'}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.get("/orchestrator/status")
def api_orchestrator_status():
    """
    Get the current orchestrator state (enabled/disabled, last run, etc.)
    """
    if not ORCHESTRATOR_AVAILABLE:
        return jsonify({"error": "Orchestrator module not available"}), 503
    
    try:
        state = orchestrator.get_orchestrator_state()
        current_run = orchestrator.get_current_repair_run()
        
        return jsonify({
            "state": state,
            "current_run": current_run
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.post("/repair/cinesync")
def api_repair_cinesync():
    """
    Manually trigger a cinesync repair run.
    Returns run ID and status immediately, then runs repair in background.
    """
    if not ORCHESTRATOR_AVAILABLE:
        return jsonify({"error": "Orchestrator module not available"}), 503
    
    try:
        # Run repair (this may take a while)
        result = repair_runner.run_cinesync_repair(trigger="manual")
        
        return jsonify({
            "success": True,
            "result": result
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.post("/repair/arr")
def api_repair_arr():
    """
    Manually trigger an ARR repair run.
    Returns run ID and status immediately, then runs repair in background.
    """
    if not ORCHESTRATOR_AVAILABLE:
        return jsonify({"error": "Orchestrator module not available"}), 503
    
    try:
        # Run repair (this may take a while)
        result = repair_runner.run_arr_repair(trigger="manual")
        
        return jsonify({
            "success": True,
            "result": result
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.get("/repair/status")
def api_repair_status():
    """
    Get the status of the current repair run, if any.
    """
    if not ORCHESTRATOR_AVAILABLE:
        return jsonify({"error": "Orchestrator module not available"}), 503
    
    try:
        current_run = orchestrator.get_current_repair_run()
        
        if current_run:
            return jsonify({
                "running": True,
                "run": current_run
            })
        else:
            return jsonify({
                "running": False,
                "run": None
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.get("/repair/history")
def api_repair_history():
    """
    Get repair run history with pagination.
    Query params: limit (default 50), offset (default 0)
    """
    if not ORCHESTRATOR_AVAILABLE:
        return jsonify({"error": "Orchestrator module not available"}), 503
    
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        
        history = orchestrator.get_repair_history(limit=limit, offset=offset)
        
        return jsonify({
            "history": history,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

app.register_blueprint(api)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8088")), debug=False)

