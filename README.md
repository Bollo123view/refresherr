# Refresherr

**Future-proof repair and refresh layer for Real-Debrid/rclone media symlinks.**

Refresherr is a self-contained container that monitors your media symlinks, detects broken links, and automatically repairs them through Cinesync or Sonarr/Radarr integration. Everything runs in a single container with a built-in web dashboard.

## Features

- 🔍 **Continuous Auto-Scan** - Background monitoring of symlinks with real-time dashboard updates
- 🔧 **Auto-Repair Orchestrator** - Configurable automatic repairs: Cinesync → ARR → manual (disabled by default)
- 🎛️ **Manual Repair Controls** - On-demand Cinesync and ARR repairs via dashboard or API
- 🌐 **Web Dashboard** - React-based UI with real-time stats, toggles, and repair history
- 🔒 **Dry-Run Mode** - Safe preview mode enabled by default (no changes until you're ready)
- 📊 **SQLite History** - Complete tracking of symlink status changes and repairs
- 🐳 **Single Container** - Everything included: scanner + API + UI + relay logic
- ⚙️ **Simple Configuration** - Just YAML + environment variables
- 🔔 **Discord Notifications** - Optional webhook notifications for repairs

## Quick Start

### Prerequisites

- Docker (or Podman)
- Media files accessible via symlinks
- Sonarr/Radarr instances (optional, for auto-repair)

### 1. Get Refresherr

```bash
git clone https://github.com/Bollo123view/refresherr.git
cd refresherr
```

### 2. Configure

Copy the sample configuration:

```bash
cp config/env.sample .env
cp config/config.sample.yaml config/config.yaml
```

Edit `.env` with your settings:

```bash
# Essential settings
DRYRUN=true                                    # Safe mode - set to false when ready
SCAN_INTERVAL=300                              # Scan every 5 minutes

# Relay settings (for ARR repairs)
RELAY_BASE=http://localhost:5050               # Internal relay (no token needed for single container)
RELAY_TOKEN=your-secret-token-here             # Only needed if exposing relay externally

# Data directory
DATA_DIR=/data

# Optional: Discord notifications
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
```

Edit `config/config.yaml` with your paths:

```yaml
scan:
  # Your media directories
  roots:
    - /opt/media/jelly/tv
    - /opt/media/jelly/movies
  
  # Verify these mounts exist before scanning
  mount_checks:
    - /mnt/remote/realdebrid
  
  interval: 300

# Route paths to Sonarr/Radarr instances
routing:
  - prefix: /opt/media/jelly/movies
    type: radarr_movie
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv

# Container ↔ host path mappings (for logs/troubleshooting)
path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Jellyfin symlink root"
  
  - container: /mnt/remote/realdebrid
    logical: /mnt/cloud/realdebrid-mount
    description: "RealDebrid mount"
```

### 3. Run

Using Docker Compose:

```bash
docker-compose up -d
```

Or using Docker directly:

```bash
docker build -t refresherr .
docker run -d \
  --name refresherr \
  --env-file .env \
  -v ./config:/config:ro \
  -v ./data:/data \
  -v /opt/media:/opt/media:rw \
  -v /mnt/realdebrid:/mnt/remote/realdebrid:ro \
  -p 8088:8088 \
  refresherr
```

### 4. Access Dashboard

Open http://localhost:8088 in your browser to:
- View symlink health statistics
- Check configuration and routing
- Monitor broken symlinks
- Trigger manual repairs
- Enable/disable auto-repair

## Configuration

### Environment Variables (`.env`)

Core settings that control Refresherr's behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_FILE` | `/config/config.yaml` | Path to YAML config |
| `DRYRUN` | `true` | Enable dry-run mode (no changes made) |
| `SCAN_INTERVAL` | `300` | Seconds between scans |
| `DATA_DIR` | `/data` | Database and logs directory |
| `RELAY_BASE` | - | Relay service URL (internal for single container) |
| `RELAY_TOKEN` | - | Auth token (only if exposing relay externally) |
| `DISCORD_WEBHOOK` | - | Optional Discord webhook URL |
| `FLASK_SECRET` | - | Session secret for dashboard |
| `PORT` | `8088` | Dashboard web port |

### YAML Configuration (`config/config.yaml`)

Defines scan roots, routing, and path mappings:

```yaml
scan:
  roots:                    # Directories to scan for symlinks
    - /opt/media/jelly/tv
    - /opt/media/jelly/movies
  
  mount_checks:             # Verify these mounts exist
    - /mnt/remote/realdebrid
  
  interval: 300             # Scan frequency in seconds

routing:                    # Route paths to instances (longest-prefix-first)
  - prefix: /opt/media/jelly/4k
    type: radarr_4k
  - prefix: /opt/media/jelly/movies
    type: radarr_movie
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv

path_mappings:              # Container ↔ host translation
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Jellyfin symlink root"
```

See `config/config.sample.yaml` for a complete example with all options.

### Volume Mounts

When running in Docker, configure volumes to match your system:

```yaml
volumes:
  - ./config:/config:ro                          # Config files (read-only)
  - ./data:/data                                 # Database and logs (read-write)
  - /opt/media/jelly:/opt/media/jelly:rw         # Symlink root (read-write for repairs)
  - /mnt/realdebrid:/mnt/remote/realdebrid:ro    # Actual files (read-only)
```

⚠️ **Important**: The left side is the **host path**, the right side is the **container path**.

### Sonarr/Radarr Configuration

For ARR repair functionality, configure your instances in `.env`:

```bash
# Sonarr instances
SONARR_TV_URL=http://sonarr-tv:8989
SONARR_TV_API=your-api-key-here

# Radarr instances
RADARR_MOVIE_URL=http://radarr:7878
RADARR_MOVIE_API=your-api-key-here

RADARR_4K_URL=http://radarr-4k:7878
RADARR_4K_API=your-api-key-here
```

### CineSync Configuration

CineSync is a **hotswap repair** feature that uses an existing media library as a source to quickly repair broken symlinks without triggering new downloads.

**How it works:**
1. You maintain a secondary library (the "CineSync library") with shows/movies
2. When a symlink breaks in your main library, CineSync searches the CineSync library for a matching file
3. If found, it replaces the broken symlink to point directly to the real file (not the CineSync symlink)
4. This provides instant repair without waiting for Sonarr/Radarr downloads

**Configuration in `.env`:**

```bash
# CineSync base folder (your secondary media library structure)
CINESYNC_BASE=/opt/media/jelly/cinesync/CineSync

# Directories to repair (where your main broken symlinks live)
CINESYNC_REPAIR_ROOTS=/opt/media/jelly/tv,/opt/media/jelly/movies

# Safety: dry-run mode (1=preview only, 0=actual repairs)
CINESYNC_DRY_RUN=1

# Limit broken symlinks to attempt per run
CINESYNC_LIMIT=200

# Security: Only create symlinks to paths starting with these prefixes
CINESYNC_ALLOWED_TARGET_PREFIXES=/mnt/remote
```

**Important Notes:**
- CineSync library must follow specific folder structure: `Shows/{Show Name}/Season N/episode.mkv`
- The CineSync folder should **NOT** be in your scan roots (see Ignore Patterns below)
- CineSync runs first in the auto-repair sequence, then ARR handles remaining breaks
- Set `CINESYNC_DRY_RUN=0` when ready to enable actual repairs

### Scanner Ignore Patterns

The scanner can skip directories and files matching specific patterns. This is **critical** for CineSync users to prevent circular repair attempts.

**Why exclude the CineSync library?**
- It's a SOURCE for repairs, not a target to monitor
- Scanning it would create duplicate/circular repair attempts
- It may contain temporary or working files you don't want to track

**Configure in `config/config.yaml`:**

```yaml
scan:
  roots:
    - /opt/media/jelly/tv
    - /opt/media/jelly/movies
    # Note: Do NOT include /opt/media/jelly/cinesync here
  
  ignore_patterns:
    - cinesync          # Skip any path containing "cinesync"
    - .tmp              # Skip temporary files
    - .partial          # Skip partial downloads
```

**Or via environment variable:**

```bash
IGNORE_SUBSTR=cinesync
```

## Usage

### Dry Run Mode (Default)

Refresherr starts in **dry-run mode** by default, which means:
- ✅ Scans symlinks and updates database
- ✅ Generates manifest showing what would be changed
- ❌ NO symlinks are modified
- ❌ NO repair actions are executed

**To disable dry-run and enable repairs:**

1. Set `DRYRUN=false` in `.env` and restart
2. OR toggle it in the dashboard header
3. OR use the API: `curl -X POST http://localhost:8088/api/config/dryrun -H "Content-Type: application/json" -d '{"dryrun": false}'`

### Auto-Scan

The scanner runs continuously in the background at the configured interval (default: 5 minutes).

**What it does:**
- Monitors all configured scan roots
- Checks symlink targets and status
- Updates database with current state
- Displays statistics in dashboard

**Configuration:**
```bash
SCAN_INTERVAL=300  # Seconds between scans (5 minutes)
```

No user action needed - scanning starts automatically when the container launches.

### Auto-Repair Orchestrator

The auto-repair orchestrator is **disabled by default** and must be explicitly enabled.

**Repair Sequence:**

When enabled, the orchestrator runs a coordinated repair workflow:

1. **🎬 CineSync Repair (First)** - Hotswap from your CineSync library
   - Fast repairs using existing files
   - No downloads needed
   - Matches show/episode/quality from CineSync folder structure
   
2. **📡 ARR Repair (Second)** - Search via Sonarr/Radarr for remaining broken links
   - Triggers searches for items CineSync couldn't fix
   - Queues downloads through your ARR instances
   - Uses configured routing to send requests to correct instance
   
3. **🔄 Post-Repair Scan** - Verify what was fixed
   - Updates database with new symlink states
   - Generates repair statistics
   - Available in dashboard and API

**To enable:**

Via Dashboard:
1. Navigate to http://localhost:8088
2. Find "Auto-Repair Orchestrator" section
3. Click toggle to enable

Via API:
```bash
curl -X POST http://localhost:8088/api/orchestrator/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

Via CLI:
```bash
# Enable
docker exec refresherr python -m refresher.cli orchestrator-toggle --enable

# Disable
docker exec refresherr python -m refresher.cli orchestrator-toggle --disable

# Check status
docker exec refresherr python -m refresher.cli orchestrator-status
```

The orchestrator state persists across container restarts.

### Manual Repairs

Use the dashboard buttons or API to trigger repairs on-demand:

**🎬 Cinesync Repair:**
- Dashboard: Click "Run Cinesync Repair Now"
- API: `curl -X POST http://localhost:8088/api/repair/cinesync`

**📡 ARR Repair:**
- Dashboard: Click "Run ARR Repair Now"
- API: `curl -X POST http://localhost:8088/api/repair/arr`

Both work independently of the orchestrator toggle.

## API Reference

### Configuration Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config` | GET | Current configuration (sensitive data masked) |
| `/api/routes` | GET | Routing and path mappings with examples |
| `/api/config/dryrun` | POST | Toggle dry-run mode |

### Status Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stats` | GET | Symlink health statistics |
| `/api/broken` | GET | List of broken symlinks |
| `/api/manifest` | GET | Dry-run manifest (preview of changes) |
| `/health` | GET | Service health check |

### Repair Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/repair/cinesync` | POST | Trigger Cinesync repair |
| `/api/repair/arr` | POST | Trigger ARR repair |
| `/api/repair/status` | GET | Current repair run status |
| `/api/repair/history` | GET | Repair history (supports `?limit=N&offset=N`) |

### Orchestrator Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/orchestrator/toggle` | POST | Enable/disable auto-repair |
| `/api/orchestrator/status` | GET | Orchestrator state and last run |

### Examples

**Check symlink health:**
```bash
curl http://localhost:8088/api/stats | jq
```

**View broken symlinks:**
```bash
curl http://localhost:8088/api/broken | jq
```

**Preview what would change (dry-run manifest):**
```bash
curl http://localhost:8088/api/manifest | jq
```

**Trigger manual repair:**
```bash
# Cinesync
curl -X POST http://localhost:8088/api/repair/cinesync

# ARR
curl -X POST http://localhost:8088/api/repair/arr
```

**Enable auto-repair:**
```bash
curl -X POST http://localhost:8088/api/orchestrator/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

## Database

Refresherr uses SQLite to track symlink status and repair history.

**Location:** `/data/symlinks.db` (configurable via `DATA_DIR`)

**Key tables:**
- `symlinks` - All scanned symlinks with status
- `repair_runs` - History of repair executions
- `repair_stats` - Per-item repair results
- `orchestrator_state` - Auto-repair configuration
- `actions` - Queued repair actions
- `movies` / `series` - Media metadata (if ingested)

**View statistics:**
```bash
docker exec refresherr python -m refresher.tools.db_stats
```

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker logs refresherr
```

Common issues:
- Missing or invalid configuration files
- Invalid YAML syntax in `config.yaml`
- Missing volume mounts

### Scans Not Running

1. Check environment: `docker exec refresherr env | grep SCAN_INTERVAL`
2. Verify mount checks: `docker exec refresherr ls -la /mnt/remote/realdebrid`
3. Review logs: `docker logs -f refresherr`

### Repairs Not Working

1. Ensure dry-run is disabled: `curl http://localhost:8088/api/config | jq '.dryrun'`
2. Check orchestrator state: `curl http://localhost:8088/api/orchestrator/status`
3. Verify ARR configuration if using ARR repairs
4. Check repair history: `curl http://localhost:8088/api/repair/history`

### Path Routing Issues

1. Check routing config: `curl http://localhost:8088/api/routes`
2. Verify path prefixes match your directory structure
3. Remember: routes are matched longest-prefix-first
4. Test with example paths in the API response

### Configuration Not Loading

1. Verify `CONFIG_FILE` points to correct location
2. Validate YAML: `python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`
3. Check file permissions and volume mounts
4. Review container logs for errors

## Security & Isolation

### Container Security

Refresherr runs as a single, self-contained container with:
- No privileged access required
- Read-only mounts for configuration and source files
- Read-write only for data directory and repair targets
- Optional read-only mounts for actual media files

**Recommended Docker security:**
```yaml
security_opt:
  - no-new-privileges:true
read_only: false  # Required for database writes
cap_drop:
  - ALL
cap_add:
  - CHOWN
  - DAC_OVERRIDE  # For symlink operations
```

### Secrets Management

**Do NOT commit secrets to version control:**
- Store sensitive data in `.env` file (add to `.gitignore`)
- Use Docker secrets or environment variables for tokens
- Keep `RELAY_TOKEN` secure if exposing relay externally
- Protect Discord webhook URLs

### Network Isolation

The single-container architecture eliminates internal network communication:
- No internal HTTP calls between services
- No authentication tokens needed for internal operations
- Relay logic runs directly within the same process

**If exposing the relay endpoint externally:**
- Set a strong `RELAY_TOKEN`
- Use reverse proxy with TLS (nginx, Traefik, Caddy)
- Restrict access by IP if possible

## Advanced Topics

### Custom Scan Roots

Define multiple scan roots in `config.yaml`:

```yaml
scan:
  roots:
    - /opt/media/jelly/tv
    - /opt/media/jelly/movies
    - /opt/media/jelly/anime
    - /opt/media/plex/4k
```

Each root is scanned independently. Use routing to direct repairs appropriately.

### Path Rewrites

Rewrite symlink targets during scanning:

```yaml
scan:
  rewrites:
    - from: /mnt/old/path
      to: /mnt/new/path
    - from: /mnt/remote/realdebrid
      to: /mnt/cloud/rd
```

Useful for:
- Migrating storage locations
- Normalizing paths across systems
- Handling multiple mount points

### Multiple ARR Instances

Configure multiple Sonarr/Radarr instances:

```bash
# In .env
SONARR_TV_URL=http://sonarr-tv:8989
SONARR_TV_API=key1

SONARR_ANIME_URL=http://sonarr-anime:8989
SONARR_ANIME_API=key2

RADARR_MOVIE_URL=http://radarr:7878
RADARR_MOVIE_API=key3

RADARR_4K_URL=http://radarr-4k:7878
RADARR_4K_API=key4
```

Then route paths appropriately in `config.yaml`.

### Metadata Ingestion

Import metadata from Sonarr/Radarr:

```bash
docker exec refresherr python -m refresher.ingest
```

This populates the database with movie/series information for enhanced dashboard features.

### CineSync Repair

Configure CineSync repair:

```bash
# In .env
CINESYNC_BASE=/opt/media/jelly/cinesync/CineSync
CINESYNC_REPAIR_ROOTS=/opt/media/jelly/tv,/opt/media/jelly/movies
```

CineSync repair hotswaps broken symlinks with files from your CineSync library.

## Building from Source

### Build the Container

```bash
docker build -t refresherr .
```

### Build the React Dashboard

The dashboard is pre-built and included in the container. To rebuild:

```bash
cd refresherr-dashboard
npm install
npm run build
```

Built files are automatically copied into the container during image build.

### Development Mode

Run services separately for development:

```bash
# Terminal 1: Backend scanner
cd app
python -m cli run

# Terminal 2: Dashboard API
cd services/dashboard
pip install -r requirements.txt
python app.py

# Terminal 3: React dev server
cd refresherr-dashboard
npm run dev
```

## Contributing

Contributions welcome! Please:
1. Test changes thoroughly in dry-run mode
2. Follow existing code style
3. Update documentation for new features
4. Include tests where applicable

## License

See [LICENSE](LICENSE) for details.

## Support

- **Issues**: https://github.com/Bollo123view/refresherr/issues
- **Discussions**: https://github.com/Bollo123view/refresherr/discussions

---

**Version:** See [VERSION](VERSION) file
