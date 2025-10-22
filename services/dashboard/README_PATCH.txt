
Refresherr Dashboard Patch — Auto unlink + action log + repairing flag
======================================================================

What this adds
--------------
- When you click "Auto search & repair" on /broken:
  1) Safely unlinks the broken symlink (removes the link only).
  2) Updates DB: symlinks.last_status='repairing', clears last_target, touches last_seen_ts.
  3) Inserts an 'enqueued' row into the 'actions' table.
  4) Calls your relay with scope=auto (unchanged).
  5) Marks the action ok/failed based on HTTP response.

Instance routing
----------------
- Basic path-based routing is included:
    /opt/media/jelly/4k      -> radarr_movie
    /opt/media/jelly/movies  -> radarr_movie
    /opt/media/jelly/tv      -> sonarr_tv
    /opt/media/jelly/hayu    -> sonarr_hayu
  Adjust INSTANCE_BY_PREFIX in app.py if your layout differs.

Required compose mount
----------------------
- The dashboard container must be able to unlink symlinks, so be sure
  docker-compose.yml has for the dashboard service:

    volumes:
      - ./data:/data:rw
      - /opt/media:/opt/media:rw

Install
-------
1) Copy app.py to services/dashboard/app.py
   Copy templates/broken.html to services/dashboard/templates/broken.html
2) Rebuild + restart dashboard:
     docker compose up -d --build dashboard
3) Test:
     curl -I http://127.0.0.1:8088/broken | head -n1
     # click "Auto search & repair" on one item
     sqlite3 ./data/symlinks.db "SELECT id,source,instance,subject_type,subject_title,scope,status FROM actions ORDER BY id DESC LIMIT 5;"

Safety
------
- The unlink step only runs if the supplied path lives under SYMLINK_ROOT (/opt/media/jelly by default) and is a symlink.
- It never touches the target file.
- DB is opened with busy_timeout and WAL is recommended for concurrency.
