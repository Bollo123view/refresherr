# Refresherr

Future-proof repair/refresh layer for RD/rclone media symlinks.

## Features

- **Mount-aware scanner** with dry-run mode enabled by default
- **Dry-run manifest** - preview all actions before applying changes
- **Discord notifications** + one-click "Find" via relay
- **SQLite history** - track all symlink status changes
- **Dockerized** - no cron needed, built-in scheduling
- **Central configuration** with path routing and container↔host mapping
- **Web Dashboard** - React-based UI with real-time stats and dry-run toggle

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Dry Run Mode](#dry-run-mode)
- [Configuration](#configuration)
- [Dashboard](#dashboard)
- [Database Schema](#database-schema)
- [Manual Tools](#manual-tools)
- [API Endpoints](#api-endpoints)
- [Troubleshooting](#troubleshooting)

## Installation

### Prerequisites

- Docker and Docker Compose installed
- Media files accessible via symlinks
- Sonarr/Radarr instances configured
- (Optional) Discord webhook for notifications

### Step 1: Clone the Repository

```bash
git clone https://github.com/Bollo123view/refresherr.git
cd refresherr
```

### Step 2: Create Configuration Files

Copy the sample configuration files:

```bash
cp config/env.sample .env
cp config/config.sample.yaml config/config.yaml
```

### Step 3: Configure Environment Variables

Edit `.env` to match your environment. Key settings:

```bash
# Dry run mode - set to 'false' to enable actual repairs (default: true)
DRYRUN=true

# Data directory for database and logs
DATA_DIR=/data

# Relay service configuration
RELAY_BASE=http://research-relay:5050
RELAY_TOKEN=your-secret-token-here

# Scan interval in seconds (default: 300 = 5 minutes)
SCAN_INTERVAL=300

# Discord webhook for notifications (optional)
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...

# Flask secret for dashboard session management
FLASK_SECRET=change-me-to-random-string
```

See `config/env.sample` for a complete list with descriptions.

### Step 4: Configure Scan Roots and Routing

Edit `config/config.yaml` to define your scan roots, routing rules, and path mappings:

```yaml
scan:
  # Directories to scan for symlinks
  roots:
    - /opt/media/jelly/tv
    - /opt/media/jelly/movies
    - /opt/media/jelly/4k
  
  # Verify these mounts exist before scanning
  mount_checks:
    - /mnt/remote/realdebrid
  
  # Scan interval in seconds
  interval: 300

# Route paths to Sonarr/Radarr instances (matched longest-prefix-first)
routing:
  - prefix: /opt/media/jelly/4k
    type: radarr_4k
  - prefix: /opt/media/jelly/movies
    type: radarr_movie
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv

# Container↔host path mappings for proper path translation
path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Jellyfin symlink root"
  
  - container: /mnt/remote/realdebrid
    logical: /mnt/cloud/realdebrid-mount
    description: "RealDebrid mount"
```

See `config/config.sample.yaml` for a complete example with all options.

### Step 5: Configure Docker Volumes

Update `docker-compose.yml` volumes to match your host paths:

```yaml
services:
  refresher:
    volumes:
      - ./config:/config:ro          # Config files (read-only)
      - ./data:/data                 # Database and logs (read-write)
      - /opt/media:/opt/media:rw     # Your symlink root (read-write for repairs)
      - /mnt/realdebrid:/mnt/remote/realdebrid:ro  # Actual files (read-only)
```

⚠️ **Important**: Ensure the paths on the left side of the `:` match your host filesystem.

### Step 6: Start the Services

```bash
docker-compose up -d
```

### Step 7: Verify Installation

Check that all services are running:

```bash
docker-compose ps
```

You should see three services running:
- `refresher` - Background scanner
- `dashboard` - Web UI and API
- `research-relay` - Search/repair relay

Access the dashboard at: `http://localhost:8088`

Check the logs to verify scanning is working:

```bash
docker-compose logs -f refresher
```

You should see scan summaries like:
```
[refresher] scan: broken=0 examined=123 dryrun=True
```

### Step 8: Configure Sonarr/Radarr Instances (Optional)

For metadata ingestion, set environment variables for your Sonarr/Radarr instances in `.env`:

```bash
SONARR_TV_URL=http://sonarr-tv:8989
SONARR_TV_API=your-api-key-here

RADARR_4K_URL=http://radarr-4k:7878
RADARR_4K_API=your-api-key-here
```

Run metadata ingest:

```bash
docker-compose exec refresher python -m refresher.ingest
```

## Quick Start

After installation, here's how to use Refresherr:

1. **Start services**: `docker-compose up -d`

2. **Access dashboard**: Open `http://localhost:8088` in your browser

3. **Review broken symlinks**: Click "Broken" in the navigation to see broken symlinks

4. **Test in dry-run mode**: The system runs in dry-run mode by default - no changes are made

5. **Review the dry-run manifest**: Check the logs or dashboard to see what would be changed

6. **Disable dry-run**: When ready, set `DRYRUN=false` in `.env` or toggle in the dashboard

7. **Monitor repairs**: Watch the dashboard for repair status and statistics

## Dry Run Mode

Refresherr includes a comprehensive dry-run mode that is **enabled by default** to ensure safe operation.

### What is Dry Run Mode?

When dry-run mode is enabled:
- ✅ Symlinks are scanned and status recorded in the database
- ✅ Broken symlinks are identified and logged
- ✅ A **manifest** is generated showing what actions would be taken
- ❌ NO symlinks are modified or removed
- ❌ NO files are moved or deleted
- ❌ NO repair actions are automatically executed

### Dry Run Manifest

The dry run manifest provides a detailed preview of all actions that would be performed:

**Manifest includes**:
- List of broken symlinks detected
- Target paths for each broken symlink
- Routing information (which Sonarr/Radarr instance would handle the repair)
- Relay URLs that would be called for repair
- Estimated scope of changes

**Viewing the manifest**:

1. **Via Logs**: 
   ```bash
   docker-compose logs refresher | grep "dry_run=True"
   ```

2. **Via API**:
   ```bash
   curl http://localhost:8088/api/broken | jq
   ```

3. **Via Dashboard**: Navigate to the "Broken" page to see all items

**Example manifest output**:
```json
{
  "summary": {
    "dryrun": true,
    "broken_count": 5,
    "examined": 1234,
    "sample": [
      {
        "path": "/opt/media/jelly/tv/Show Name/Season 1/episode.mkv",
        "target": "/mnt/remote/realdebrid/torrents/123/episode.mkv",
        "kind": "tv",
        "name": "Show Name",
        "action": "would_enqueue_repair",
        "relay_url": "http://relay:5050/find?type=sonarr_tv&term=Show%20Name"
      }
    ]
  }
}
```

### Enabling/Disabling Dry Run

**Method 1: Environment Variable**

Edit `.env`:
```bash
DRYRUN=true   # Enable dry-run (default)
DRYRUN=false  # Disable dry-run (allow repairs)
```

Then restart:
```bash
docker-compose restart refresher
```

**Method 2: Dashboard Toggle** (see [Dashboard](#dashboard) section)

Click the "Dry Run Mode" toggle in the dashboard header to enable/disable on-the-fly.

**Method 3: Configuration File**

Environment variables override YAML settings, so use `.env` for most cases.

### Best Practices

1. **Always start with dry-run enabled** (default)
2. **Review the manifest** before disabling dry-run
3. **Test with a small scan root** first
4. **Monitor logs** when dry-run is disabled
5. **Re-enable dry-run** if unexpected behavior occurs

## Configuration

Refresherr uses a centralized configuration system that supports both YAML files and environment variables.

### Configuration File (`config/config.yaml`)

The YAML configuration file defines:
- **Scan roots**: Directories to monitor for symlinks
- **Routing**: Map path prefixes to Sonarr/Radarr instances
- **Path mappings**: Container↔host path translation for proper containerized operation
- **Relay settings**: Research relay service configuration
- **Database settings**: SQLite database location
- **Notification settings**: Discord webhooks and notification preferences

See `config/config.yaml` for a complete example with comments.

### Environment Variables (`.env`)

Environment variables override YAML settings and provide sensitive data like tokens. Key variables:

- `CONFIG_FILE`: Path to YAML config (default: `/config/config.yaml`)
- `DRYRUN`: Enable/disable dry-run mode (`true`/`false`)
- `SCAN_INTERVAL`: Seconds between scans (default: `300`)
- `RELAY_BASE`: Relay service URL
- `RELAY_TOKEN`: Authentication token for relay
- `DATA_DIR`: Database and logs directory (default: `/data`)
- `DISCORD_WEBHOOK`: Discord notification webhook URL

See `config/env.sample` for a complete list with descriptions.

### Path Routing

Refresherr routes symlinks to the correct Sonarr/Radarr instance based on path prefixes. Routes are matched longest-prefix-first:

```yaml
routing:
  - prefix: /opt/media/jelly/hayu
    type: sonarr_hayu
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv
  - prefix: /opt/media/jelly/4k
    type: radarr_4k
```

**Example**: A broken symlink at `/opt/media/jelly/hayu/Show/Season 1/episode.mkv` will route to `sonarr_hayu` for automatic repair.

### Path Mappings (Container ↔ Host)

When running in containers, paths inside the container may differ from paths on the host. Path mappings enable proper translation:

```yaml
path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Jellyfin symlink root"
  
  - container: /mnt/remote/realdebrid
    logical: /mnt/cloud/realdebrid-mount
    description: "RealDebrid rclone mount"
```

This ensures logs, debugging output, and API responses can reference both container and host paths for easier troubleshooting.

### Recommended Volume Mounts

When running Refresherr in Docker, configure volumes in `docker-compose.yml`:

```yaml
volumes:
  # Config files (read-only)
  - ./config:/config:ro
  
  # Data directory (read-write for database)
  - ./data:/data
  
  # Media symlink root (read-write for repairs)
  - /opt/media:/opt/media:rw
  
  # Actual file mount (read-only)
  - /mnt/realdebrid:/mnt/remote/realdebrid:ro
```

The left side of each volume mount is the **host path**, and the right side is the **container path**. Use path mappings in your config to document these relationships for proper path translation in logs and the dashboard.

## API Endpoints

Refresherr exposes several API endpoints for integration and debugging:

- `GET /api/config` - Current configuration (with sensitive data masked)
- `GET /api/routes` - Routing and path mapping information with examples
- `GET /api/stats` - Symlink health statistics
- `GET /api/broken` - List of broken symlinks
- `GET /api/movies` - Movie library data
- `GET /api/episodes` - Episode library data

### Example: Viewing Configuration

```bash
curl http://localhost:8088/api/config | jq
```

```json
{
  "scan": {
    "roots": ["/opt/media/jelly/tv", "/opt/media/jelly/hayu"],
    "interval": 300
  },
  "routing": [
    {"prefix": "/opt/media/jelly/hayu", "type": "sonarr_hayu"},
    {"prefix": "/opt/media/jelly/tv", "type": "sonarr_tv"}
  ],
  "path_mappings": [
    {
      "container_path": "/opt/media/jelly",
      "logical_path": "/mnt/storage/media/jelly",
      "description": "Jellyfin symlink root"
    }
  ]
}
```

### Example: Viewing Routes with Examples

```bash
curl http://localhost:8088/api/routes | jq
```

This endpoint provides routing configuration along with practical examples for troubleshooting.

## Dashboard

The web-based dashboard provides a user-friendly interface for monitoring and managing Refresherr.

### Features

- **Real-time statistics**: View symlink health, broken counts, and repair status
- **Dry-run toggle**: Enable/disable dry-run mode with one click
- **Configuration visibility**: See current routing, path mappings, and settings
- **Broken symlink list**: Browse and manually trigger repairs for broken symlinks
- **Movie/Episode library**: View symlinked content from your Sonarr/Radarr instances
- **Responsive design**: Works on desktop and mobile devices

### Accessing the Dashboard

The dashboard runs on port 8088 by default:

```
http://localhost:8088
```

Or from another machine:

```
http://YOUR_SERVER_IP:8088
```

### Dry Run Toggle

The dashboard header includes a prominent **Dry Run Mode** toggle:

- **Toggle ON (default)**: Dry-run mode enabled - safe preview mode
- **Toggle OFF**: Dry-run mode disabled - repairs will be executed

The toggle state is synchronized with the backend and persists across sessions.

**Visual indicators**:
- 🟢 **Green toggle** = Dry-run ON (safe mode)
- 🔴 **Red toggle** = Dry-run OFF (active repairs)

### Dashboard Pages

1. **Home** (`/`): Overview with statistics and health metrics
2. **Broken** (`/broken`): List of broken symlinks with repair actions
3. **Movies** (`/movies`): Movie library from Radarr
4. **Episodes** (`/episodes`): Episode library from Sonarr

### Building the React Dashboard (Development)

For development or customization:

```bash
cd dashboard
npm install
npm run build
```

The built static assets can be served by the backend at `/static` (planned for unified deployment).

## Database Schema

Refresherr uses SQLite to track symlink status, repair actions, and media metadata.

### Database Location

Default: `/data/symlinks.db` (configurable via `DATA_DIR` environment variable)

### Core Tables

**symlinks** - Tracks all scanned symlinks
- `path` (PRIMARY KEY): Full path to the symlink
- `last_target`: Target path the symlink points to
- `status`: Current status (ok, broken, repairing)
- `last_status`: Most recent status for compatibility
- `first_seen_utc`: When first discovered
- `last_seen_utc`: Last scan timestamp

**actions** - Queued repair/search actions
- `id` (PRIMARY KEY): Auto-incrementing action ID
- `url`: Relay URL to invoke for repair
- `status`: Action status (pending, sent, failed)
- `reason`: Why action was created (e.g., auto-search)
- `related_path`: Associated symlink path
- `created_utc`: When action was queued
- `fired_utc`: When action was executed
- `last_error`: Error message if failed

### Media Metadata Tables

**movies** - Radarr movie metadata
- Links to `movie_files` for symlink tracking

**series** - Sonarr series metadata
- Links to `episode_files` for symlink tracking

**movie_files** / **episode_files** - File metadata with symlink paths
- Ingested from Sonarr/Radarr APIs
- Links library content to symlinks

### Database Operations

**View database statistics**:
```bash
docker-compose exec refresher python -m refresher.tools.db_stats
```

**Reset database** (⚠️ DESTRUCTIVE):
```python
from refresher.core import db
db.nuke_database(confirm=True)
```

For detailed schema documentation, see the source code in `app/refresher/core/db.py`.

## Manual Tools

Refresherr includes manual tools for safe, step-by-step operations without automatic behavior.

### Available Tools

**1. Database Statistics** - View symlink status counts

```bash
docker-compose exec refresher python -m refresher.tools.db_stats
```

Shows:
- Total symlinks scanned
- Broken vs. OK counts
- Top directories with issues

**2. Queue Repairs** - Manually queue repair actions

```bash
docker-compose exec refresher python -m refresher.tools.queue_repairs
```

Environment variables needed:
- `RELAY_BASE`: Relay service URL
- `RELAY_TOKEN`: Auth token
- `ROUTE_MAP`: Path-to-instance mapping
- `QUEUE_LIMIT`: Max actions to queue (default: 25)

**3. Process Actions** - Execute queued actions

```bash
docker-compose exec refresher python -m refresher.tools.process_actions
```

Options:
- Set `ACTIONS_DRY_RUN=1` for preview mode
- Set `ACTIONS_MAX=N` to limit execution count

**4. Repair Season** - Repair a specific season

Located at `app/refresher/tools/repair_season.py`, this tool repairs symlinks for a specific show and season.

**5. CineSync Repair** - Match broken symlinks to CineSync library

Located at `app/refresher/tools/cinesync_repair.py`, this tool can repair symlinks using an alternative file source.

### Safety Features

All manual tools:
- ✅ Require explicit execution
- ✅ Support dry-run mode
- ✅ Log all actions to database
- ✅ Never auto-delete or quarantine files
- ✅ Preview changes before applying

## API Endpoints

Refresherr exposes REST API endpoints for integration, automation, and debugging.

### Configuration Endpoints

**GET `/api/config`** - Current configuration (sensitive data masked)

```bash
curl http://localhost:8088/api/config | jq
```

Response includes:
- Scan roots and interval
- Routing configuration
- Path mappings
- Dry-run status
- Database location

**GET `/api/routes`** - Routing and path mapping with examples

```bash
curl http://localhost:8088/api/routes | jq
```

Shows:
- Route prefixes and target instances
- Container↔host path mappings
- Example paths for each route

### Data Endpoints

**GET `/api/stats`** - Symlink health statistics

```bash
curl http://localhost:8088/api/stats | jq
```

Returns counts for:
- Total/broken/OK symlinks
- Movies linked/total
- Episodes linked/total
- Health percentages

**GET `/api/broken`** - List of broken symlinks

```bash
curl http://localhost:8088/api/broken | jq
```

Returns array of broken symlink objects with paths, targets, and metadata.

**GET `/api/movies`** - Movie library data

Returns all symlinked movies from Radarr instances.

**GET `/api/episodes`** - Episode library data

Returns all symlinked episodes from Sonarr instances.

### Health Endpoints

**GET `/health`** - Service health check

Returns `{"ok": true}` if database is accessible.

**GET `/dbcheck`** - Database table verification

Shows row counts for all tables and schema information.

### Example API Usage

**Check if dry-run is enabled**:
```bash
curl -s http://localhost:8088/api/config | jq '.dryrun'
```

**Get broken symlink count**:
```bash
curl -s http://localhost:8088/api/stats | jq '.symlinks.broken'
```

**View routing for troubleshooting**:
```bash
curl -s http://localhost:8088/api/routes | jq '.examples'
```

## Troubleshooting

### Path Routing Issues

If symlinks are routing to the wrong instance:

1. Check routing configuration: `curl http://localhost:8088/api/routes`
2. Verify path prefixes match your directory structure
3. Remember routes are matched longest-prefix-first
4. Check the examples provided by the API for expected behavior

### Path Mapping Issues

If paths look incorrect in logs or the dashboard:

1. Check path mappings: `curl http://localhost:8088/api/config`
2. Verify volume mounts in `docker-compose.yml` match your path mappings
3. Ensure container paths align with the paths in your config file

### Configuration Not Loading

1. Check `CONFIG_FILE` environment variable points to the correct file
2. Verify YAML syntax: `python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`
3. Check file permissions and volume mounts
4. Review container logs: `docker logs refresher`

### Dry Run Mode Not Working

If repairs are happening when dry-run should be enabled:

1. Check environment: `docker-compose exec refresher env | grep DRYRUN`
2. Verify config: `curl http://localhost:8088/api/config | jq '.dryrun'`
3. Restart services after changing `.env`: `docker-compose restart`
4. Check logs for dry-run status in scan output

### Database Issues

**Database locked errors**:
1. Ensure only one scanner instance is running
2. Check for long-running queries
3. Increase timeout in code if needed

**Corrupted database**:
```bash
# Backup first
cp /data/symlinks.db /data/symlinks.db.backup

# Check integrity
sqlite3 /data/symlinks.db "PRAGMA integrity_check;"
```

### Mount Not Found Errors

If scanner reports "mount not present":

1. Verify mount exists: `ls -la /mnt/remote/realdebrid`
2. Check Docker volume mounts in `docker-compose.yml`
3. Ensure mount is accessible inside container: `docker exec refresher ls -la /mnt/remote/realdebrid`
4. Review `mount_checks` in config file

### Getting Help

1. Check logs: `docker-compose logs -f refresher`
2. Review API responses for diagnostic info
3. Use manual tools to test individual operations
4. Open an issue on GitHub with logs and configuration (redact secrets!)

## Additional Documentation

For more detailed information, see:

- **[Deployment Guide](DEPLOYMENT.md)** - Complete deployment documentation including unified backend approach
- **[Dashboard UX Guide](DASHBOARD_UX_GUIDE.md)** - Dashboard usage, troubleshooting, and routing visibility
- **[Usage Examples](USAGE_EXAMPLES.md)** - Common workflows and practical examples
- **[Implementation Details](IMPLEMENTATION_SUMMARY.md)** - Technical implementation notes

## License

See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please:
1. Test changes thoroughly in dry-run mode first
2. Follow existing code style and conventions
3. Update documentation for any new features
4. Include tests where applicable

## Changelog

See commit history for detailed changes. Major updates:
- **2026-01**: Added dry-run manifest feature, consolidated documentation, dashboard toggle
- **2025-12**: Central configuration system with path routing and mappings
- **2025-11**: React dashboard with real-time statistics
- **2025-10**: Initial release with symlink scanning and repair
