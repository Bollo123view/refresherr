# Database Schema Documentation

## Overview

Refresherr uses a centralized SQLite database (`symlinks.db`) to track symlinks, repair actions, and media metadata. All database operations are managed through the central `app/refresher/core/db.py` module.

## Database Location

Default location: `/data/symlinks.db` (configurable via `DATA_DIR` environment variable)

## Central DB Module

The `app/refresher/core/db.py` module provides:

- **Centralized connection management**: `get_connection()`
- **Versioned schema migrations**: Automatic upgrades when schema version changes
- **Consistent initialization**: `initialize_schema()`
- **Database reset capability**: `nuke_database()` for clean slate (requires explicit confirmation)
- **Thread-safe operations**: All write operations use locking

## Schema Version

Current version: **v1**

The database tracks its schema version in the `schema_version` table. When the application starts, it automatically applies any necessary migrations to bring the database up to the current version.

## Core Tables

### schema_version

Tracks database schema version history.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-incrementing ID |
| version | INTEGER | Schema version number |
| applied_utc | TEXT | ISO 8601 timestamp when version was applied |

### symlinks

Tracks all scanned symlinks and their status.

| Column | Type | Description |
|--------|------|-------------|
| path | TEXT PRIMARY KEY | Full path to the symlink |
| last_target | TEXT | The target path the symlink points to |
| status | TEXT | Current status (ok, broken) |
| last_status | TEXT | Most recent status (for compatibility) |
| first_seen_utc | TEXT | ISO 8601 timestamp when first discovered |
| last_seen_utc | TEXT | ISO 8601 timestamp of last scan |

**Purpose**: The scanner periodically checks all symlinks in configured directories. This table maintains a history of each symlink's health status over time.

### actions

Queues repair/search actions to be executed.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-incrementing action ID |
| url | TEXT | URL to invoke (usually relay find/search endpoint) |
| status | TEXT | Action status (pending, sent, failed) |
| reason | TEXT | Why this action was created (e.g., auto-search) |
| related_path | TEXT | Associated symlink path |
| created_utc | TEXT | ISO 8601 timestamp when action was created |
| fired_utc | TEXT | ISO 8601 timestamp when action was executed |
| last_error | TEXT | Error message if action failed |

**Indexes**:
- `idx_actions_status` on `status`
- `idx_actions_related_path` on `related_path`

**Purpose**: When broken symlinks are detected, repair actions (typically search URLs) are queued here. The `process_actions` tool picks these up and executes them.

## Media Metadata Tables

These tables store metadata ingested from Sonarr and Radarr instances.

### movies

Radarr movie metadata.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Movie ID |
| instance | TEXT | Radarr instance name |
| radarr_id | INTEGER | Radarr's internal movie ID |
| title | TEXT | Movie title |
| year | INTEGER | Release year |
| imdb_id | TEXT | IMDb identifier |
| tmdb_id | INTEGER | TMDb identifier |
| monitored | INTEGER | 1 if monitored in Radarr, 0 otherwise |
| added_utc | TEXT | When added to Radarr |
| poster_url | TEXT | URL to movie poster |
| fanart_url | TEXT | URL to fanart image |

**Indexes**:
- `ix_movies_instance` on `instance`
- `uq_movies_instance_radarr` unique index on `(instance, radarr_id)`

### movie_files

Radarr movie file metadata and symlink tracking.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | File ID |
| instance | TEXT | Radarr instance name |
| radarr_movie_id | INTEGER | Associated movie ID in Radarr |
| radarr_file_id | INTEGER | Radarr's internal file ID |
| quality | TEXT | Quality profile name |
| resolution | INTEGER | Resolution (e.g., 1080) |
| video_codec | TEXT | Video codec (e.g., h264) |
| audio_codec | TEXT | Audio codec |
| size_bytes | INTEGER | File size in bytes |
| original_path | TEXT | Original file path in Radarr |
| symlink_path | TEXT | Path to symlink (if exists) |

**Indexes**:
- `ix_movie_files_inst_mid` on `(instance, radarr_movie_id)`

**Purpose**: Links Radarr files to their symlinks tracked in the `symlinks` table.

### series

Sonarr series metadata.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Series ID |
| instance | TEXT | Sonarr instance name |
| sonarr_id | INTEGER | Sonarr's internal series ID |
| title | TEXT | Series title |
| imdb_id | TEXT | IMDb identifier |
| tvdb_id | INTEGER | TheTVDB identifier |
| tmdb_id | INTEGER | TMDb identifier |
| monitored | INTEGER | 1 if monitored in Sonarr, 0 otherwise |
| poster_url | TEXT | URL to series poster |
| fanart_url | TEXT | URL to fanart image |

**Indexes**:
- `ix_series_instance` on `instance`
- `uq_series_instance_sid` unique index on `(instance, sonarr_id)`

### episode_files

Sonarr episode file metadata and symlink tracking.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | File ID |
| instance | TEXT | Sonarr instance name |
| sonarr_series_id | INTEGER | Associated series ID in Sonarr |
| sonarr_file_id | INTEGER | Sonarr's internal file ID |
| season_number | INTEGER | Season number |
| quality | TEXT | Quality profile name |
| resolution | INTEGER | Resolution (e.g., 1080) |
| release_group | TEXT | Release group name |
| size_bytes | INTEGER | File size in bytes |
| original_path | TEXT | Original file path in Sonarr |
| symlink_path | TEXT | Path to symlink (if exists) |

**Indexes**:
- `ix_episode_files_inst_sid` on `(instance, sonarr_series_id)`

**Purpose**: Links Sonarr episode files to their symlinks tracked in the `symlinks` table.

### events

Historical event log for broken symlinks and repair actions.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-incrementing event ID |
| ts | INTEGER | Unix timestamp |
| path | TEXT | Symlink path |
| target | TEXT | Target path (if readable) |
| kind | TEXT | Media type classification |
| name | TEXT | Show/movie name |
| action | TEXT | Action taken |
| status | TEXT | Event status |

**Purpose**: Maintains a historical log of events for analysis and debugging.

## Tool-Specific Tables

Some tools create additional tables for their specific needs. These are documented here for completeness.

### cinesync_items (used by cinesync_repair.py)

Indexes CineSync library content for matching broken symlinks.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Item ID |
| tmdb_id | INTEGER | TMDb identifier |
| show_title | TEXT | Show title |
| show_norm | TEXT | Normalized show title for matching |
| year | INTEGER | Release year |
| season | INTEGER | Season number |
| episode | INTEGER | Episode number |
| path | TEXT UNIQUE | Path to file in CineSync |
| target_ok | INTEGER | 1 if symlink target exists, 0 otherwise |
| resolution_rank | INTEGER | Quality ranking for preference |
| first_seen_utc | INTEGER | Unix timestamp when first indexed |
| last_seen_utc | INTEGER | Unix timestamp of last scan |

### cinesync_runs (used by cinesync_repair.py)

Tracks CineSync repair runs and their statistics.

| Column | Type | Description |
|--------|------|-------------|
| run_id | INTEGER PRIMARY KEY | Run ID |
| started_utc | INTEGER | Unix timestamp when run started |
| finished_utc | INTEGER | Unix timestamp when run finished |
| dry_run | INTEGER | 1 if dry run, 0 otherwise |
| repair_roots | TEXT | Comma-separated list of repair roots |
| cinesync_base | TEXT | CineSync base path |
| allowed_prefixes | TEXT | Allowed target path prefixes |
| indexed_count | INTEGER | Number of items indexed |
| checked_broken | INTEGER | Number of broken symlinks checked |
| candidate_found | INTEGER | Number of candidates found |
| resolved_target_ok | INTEGER | Number with valid resolved targets |
| replaced | INTEGER | Number of symlinks replaced |
| skipped | INTEGER | Number skipped |
| errors | INTEGER | Number of errors encountered |

## Database Operations

### Initialization

On first run or when schema version changes, the database is automatically initialized/upgraded:

```python
from app.refresher.core import db

conn = db.get_connection()
db.initialize_schema(conn)
```

### Common Operations

**Record a symlink**:
```python
db.record_symlink("/path/to/symlink", "/path/to/target", "ok")
```

**Enqueue a repair action**:
```python
db.enqueue_action("http://relay/find?...", reason="auto-search", related_path="/path/to/symlink")
```

**Get pending actions**:
```python
actions = db.get_pending_actions(limit=25)
for action in actions:
    print(action["url"])
```

**Mark action as completed**:
```python
db.mark_action_sent(action_id, ok=True)
```

### Database Reset

**WARNING**: This permanently deletes all data!

```python
from app.refresher.core import db

# Must explicitly confirm
db.nuke_database(confirm=True)
```

This will:
1. Drop all tables
2. Recreate the schema at the current version
3. Start with a clean database

## Migration Strategy

When schema changes are needed:

1. Increment `SCHEMA_VERSION` in `db.py`
2. Add a new `_create_vX_schema()` or `_migrate_vX_to_vY()` function
3. Update `initialize_schema()` to apply the new migration
4. Document the changes in this README

Example:
```python
if current_version < 2:
    _migrate_v1_to_v2(conn)
    conn.execute(
        "INSERT INTO schema_version (version, applied_utc) VALUES (?, ?)",
        (2, dt.datetime.utcnow().isoformat())
    )
    conn.commit()
    current_version = 2
```

## Best Practices

1. **Always use the central DB module**: Import `from app.refresher.core import db`, don't create connections directly
2. **Use connection pooling sparingly**: SQLite works best with short-lived connections
3. **Enable WAL mode**: Already done automatically by `get_connection()`
4. **Handle concurrent access**: The central module provides thread-safe operations for writes
5. **Close connections**: When using `get_connection()` directly, close the connection when done
6. **Test migrations**: Always test schema migrations with real data before deploying

## Monitoring

Use the `db_stats.py` tool to monitor database health:

```bash
python -m app.refresher.tools.db_stats
```

This displays:
- Symlink status counts (ok vs broken)
- Top directories with broken symlinks
- Overall database statistics

## Troubleshooting

**Database locked errors**:
- Ensure WAL mode is enabled (done automatically)
- Check for long-running transactions
- Increase busy timeout if needed

**Schema version mismatch**:
- The application automatically migrates on startup
- Check logs for migration errors
- As last resort, backup and use `nuke_database()` to recreate

**Corrupted database**:
```bash
# Backup first
cp /data/symlinks.db /data/symlinks.db.backup

# Check integrity
sqlite3 /data/symlinks.db "PRAGMA integrity_check;"

# If corrupted, restore or nuke and re-scan
```

## Related Tools

- **scanner.py**: Scans directories and populates `symlinks` table
- **process_actions.py**: Executes queued actions from `actions` table
- **queue_repairs.py**: Creates actions for broken symlinks
- **ingest.py**: Populates media metadata tables from Sonarr/Radarr
- **db_stats.py**: Display database statistics
- **cinesync_repair.py**: Repairs broken symlinks using CineSync library

## Further Reading

- Main README: [README.md](README.md)
- SQLite WAL mode: https://www.sqlite.org/wal.html
- SQLite best practices: https://www.sqlite.org/bestpractice.html
