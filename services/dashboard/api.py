# services/dashboard/api.py
from flask import Blueprint, jsonify
# import your real data providers:
# from .data import get_broken_items, get_movies, get_episodes

api = Blueprint("api", __name__, url_prefix="/api")

def get_broken_items():
    # TODO: replace with your real source
    return []

def get_movies():
    return []

def get_episodes():
    return []

def _unified_item(it):
    """Normalize to a shared DTO for Broken/Movies/Episodes cards."""
    kind = it.get("kind") or ("episode" if it.get("is_tv") else "movie")
    title = it.get("series_title") or it.get("movie_title") or it.get("display_title") or it.get("title") or it.get("name")
    return {
        "kind": kind,
        "title": title,
        "season": it.get("season"),
        "episode": it.get("episode"),
        "year": it.get("year"),
        "status": it.get("status", "ok"),
        "reason": it.get("reason"),
        "can_repair": bool(it.get("can_repair", True if it.get("status") == "broken" else False)),
        "ids": {
            "jellyfin": it.get("jellyfin_id"),
            "tmdb": it.get("tmdb_id"),
        },
        "paths": {
            "library": it.get("library_path"),
            "target": it.get("target_path"),
        },
    }

@api.get("/broken")
def api_broken():
    return jsonify([_unified_item(x) | {"status": "broken"} for x in get_broken_items()])

@api.get("/movies")
def api_movies():
    return jsonify([_unified_item(x) | {"kind": "movie"} for x in get_movies()])

@api.get("/episodes")
def api_episodes():
    return jsonify([_unified_item(x) | {"kind": "episode"} for x in get_episodes()])

