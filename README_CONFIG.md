# Configuration and Routing Guide

This guide explains how to configure Refresherr's centralized configuration system, including path routing and container↔host path mappings.

## Table of Contents

1. [Overview](#overview)
2. [Configuration Sources](#configuration-sources)
3. [Configuration File Structure](#configuration-file-structure)
4. [Path Routing](#path-routing)
5. [Path Mappings](#path-mappings)
6. [Environment Variables](#environment-variables)
7. [API Endpoints](#api-endpoints)
8. [Troubleshooting](#troubleshooting)

## Overview

Refresherr uses a centralized configuration system (`refresher/config.py`) that:

- Loads settings from YAML files and environment variables
- Provides path routing to map symlink locations to Sonarr/Radarr instances
- Enables container↔host path translation for proper containerized operation
- Exposes configuration via REST API for UI and debugging

## Configuration Sources

Configuration is loaded in this order (later sources override earlier ones):

1. **YAML file** (`config/config.yaml` by default)
2. **Environment variables** (`.env` file or Docker environment)
3. **Defaults** (built into the config module)

## Configuration File Structure

### Main Sections

```yaml
scan:           # Scanner configuration
relay:          # Relay service settings
routing:        # Path-based instance routing
path_mappings:  # Container↔host path mappings
database:       # Database settings
notifications:  # Notification configuration
```

### Complete Example

```yaml
# config/config.yaml

scan:
  # Directories to scan for symlinks
  roots:
    - /opt/media/jelly/tv
    - /opt/media/jelly/movies
    - /opt/media/jelly/4k
  
  # Verify these mounts exist before scanning
  mount_checks:
    - /mnt/remote/realdebrid
  
  # Path rewrites (transform symlink targets)
  rewrites:
    - from: /mnt/remote/realdebrid
      to: /mnt/cloud/rd
  
  # Scan interval in seconds
  interval: 300
  
  # Patterns to ignore
  ignore_patterns:
    - cinesync
    - .tmp

# Route paths to Sonarr/Radarr instances
# Matched longest-prefix-first
routing:
  - prefix: /opt/media/jelly/4k
    type: radarr_4k
  - prefix: /opt/media/jelly/movies
    type: radarr_movie
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv

# Container↔host path mappings
path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Jellyfin symlink root"
  
  - container: /mnt/remote/realdebrid
    logical: /mnt/cloud/realdebrid-mount
    description: "RealDebrid mount"

# Relay service configuration
relay:
  base_env: RELAY_BASE
  token_env: RELAY_TOKEN

# Database configuration
database:
  data_dir: /data

# Notifications
notifications:
  enabled: true
```

## Path Routing

Path routing determines which Sonarr/Radarr instance handles broken symlinks in a given directory.

### How It Works

1. A broken symlink is detected at a specific path
2. The path is matched against routing rules (longest prefix first)
3. The symlink is routed to the corresponding instance for automatic repair

### Example

With this routing configuration:

```yaml
routing:
  - prefix: /opt/media/jelly/4k
    type: radarr_4k
  - prefix: /opt/media/jelly/movies
    type: radarr_movie
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv
```

**Symlink paths are routed as follows:**

| Symlink Path | Routes To | Why |
|-------------|-----------|-----|
| `/opt/media/jelly/4k/Movie (2023)/movie.mkv` | `radarr_4k` | Matches `/opt/media/jelly/4k` prefix |
| `/opt/media/jelly/movies/Movie/file.mkv` | `radarr_movie` | Matches `/opt/media/jelly/movies` prefix |
| `/opt/media/jelly/tv/Show/Season 1/ep.mkv` | `sonarr_tv` | Matches `/opt/media/jelly/tv` prefix |

### Order Matters

Routes are matched **longest-prefix-first**. This ensures more specific paths override general ones:

```yaml
routing:
  - prefix: /opt/media/jelly/tv/special
    type: sonarr_special
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv
```

Result: `/opt/media/jelly/tv/special/Show/file.mkv` → `sonarr_special`  
Result: `/opt/media/jelly/tv/Show/file.mkv` → `sonarr_tv`

### Viewing Current Routes

Query the API to see active routing:

```bash
curl http://localhost:8088/api/routes | jq '.routing'
```

## Path Mappings

Path mappings enable translation between container paths (inside Docker) and logical/host paths (outside Docker).

### Why Path Mappings?

When running in containers:
- **Inside container**: `/opt/media/jelly/tv/Show/file.mkv`
- **On host system**: `/mnt/storage/media/jelly/tv/Show/file.mkv`

Path mappings make these relationships explicit for:
- Clearer log messages
- Better API responses
- Easier troubleshooting
- External tool integration

### Configuration

```yaml
path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Main media library"
  
  - container: /mnt/remote/realdebrid
    logical: /mnt/cloud/realdebrid-mount
    description: "RealDebrid rclone mount"
```

### Usage in Code

```python
from refresher.config import load_config, container_to_logical, logical_to_container

config = load_config()

# Translate container → logical
container_path = "/opt/media/jelly/tv/Show/file.mkv"
logical_path = container_to_logical(container_path, config.path_mappings)
# Result: "/mnt/storage/media/jelly/tv/Show/file.mkv"

# Translate logical → container
back = logical_to_container(logical_path, config.path_mappings)
# Result: "/opt/media/jelly/tv/Show/file.mkv"
```

### Viewing Current Mappings

```bash
curl http://localhost:8088/api/routes | jq '.path_mappings'
```

## Environment Variables

Environment variables override YAML settings. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_FILE` | `/config/config.yaml` | Path to YAML config file |
| `DRYRUN` | `true` | Enable dry-run mode (no actual changes) |
| `SCAN_INTERVAL` | `300` | Seconds between scans |
| `DATA_DIR` | `/data` | Database and logs directory |
| `RELAY_BASE` | _(none)_ | Relay service base URL |
| `RELAY_TOKEN` | _(none)_ | Relay authentication token |
| `DISCORD_WEBHOOK` | _(none)_ | Discord webhook URL |
| `REFRESHER_LOG_LEVEL` | `INFO` | Logging level |
| `IGNORE_SUBSTR` | _(none)_ | Pattern to ignore in paths |

### Example `.env` File

```bash
CONFIG_FILE=/config/config.yaml
DRYRUN=false
SCAN_INTERVAL=300
DATA_DIR=/data
RELAY_BASE=http://research-relay:5050
RELAY_TOKEN=your-secret-token
DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
REFRESHER_LOG_LEVEL=INFO
```

See `.env.sample` for a complete example with comments.

## API Endpoints

Refresherr exposes several API endpoints for configuration visibility and debugging.

### GET `/api/config`

Returns the current configuration (with sensitive data masked).

```bash
curl http://localhost:8088/api/config | jq
```

**Response:**
```json
{
  "scan": {
    "roots": ["/opt/media/jelly/tv", "/opt/media/jelly/movies"],
    "interval": 300,
    "ignore_patterns": ["cinesync", ".tmp"]
  },
  "routing": [
    {"prefix": "/opt/media/jelly/4k", "type": "radarr_4k"},
    {"prefix": "/opt/media/jelly/tv", "type": "sonarr_tv"}
  ],
  "path_mappings": [
    {
      "container_path": "/opt/media/jelly",
      "logical_path": "/mnt/storage/media/jelly",
      "description": "Main media library"
    }
  ],
  "dryrun": true,
  "log_level": "INFO"
}
```

### GET `/api/routes`

Returns routing and path mapping configuration with examples.

```bash
curl http://localhost:8088/api/routes | jq
```

**Response:**
```json
{
  "routing": [
    {"prefix": "/opt/media/jelly/4k", "type": "radarr_4k"},
    {"prefix": "/opt/media/jelly/tv", "type": "sonarr_tv"}
  ],
  "path_mappings": [
    {
      "container_path": "/opt/media/jelly",
      "logical_path": "/mnt/storage/media/jelly",
      "description": "Main media library"
    }
  ],
  "examples": [
    {
      "path": "/opt/media/jelly/4k/Movie/file.mkv",
      "routes_to": "radarr_4k",
      "description": "Content under /opt/media/jelly/4k routes to radarr_4k"
    }
  ]
}
```

### GET `/api/stats`

Returns symlink health statistics.

```bash
curl http://localhost:8088/api/stats | jq
```

## Troubleshooting

### Configuration Not Loading

**Problem:** Config changes don't take effect.

**Solutions:**
1. Verify `CONFIG_FILE` environment variable points to correct file
2. Check YAML syntax: `python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"`
3. Check file permissions: `ls -la config/config.yaml`
4. Verify volume mounts in `docker-compose.yml`
5. Restart the service: `docker-compose restart refresher`

### Wrong Instance Selected

**Problem:** Broken symlinks route to wrong Sonarr/Radarr instance.

**Solutions:**
1. Check routing: `curl http://localhost:8088/api/routes | jq '.routing'`
2. Verify path prefixes match your directory structure exactly
3. Remember: routes are matched longest-prefix-first
4. Check example paths in API response for expected behavior
5. Ensure no typos in `type` values (must match relay service configuration)

### Path Mapping Issues

**Problem:** Paths look incorrect in logs or dashboard.

**Solutions:**
1. Check mappings: `curl http://localhost:8088/api/config | jq '.path_mappings'`
2. Verify volume mounts in `docker-compose.yml` align with path mappings
3. Ensure container paths match what's inside the Docker container
4. Ensure logical paths match the host filesystem
5. Check path mapping examples in API response

### Mount Check Failures

**Problem:** Scanner reports "mount not present" error.

**Solutions:**
1. Verify mount points exist: `ls -la /mnt/remote/realdebrid`
2. Check Docker volume mounts in `docker-compose.yml`
3. Ensure mount is accessible inside container: `docker exec refresher ls -la /mnt/remote/realdebrid`
4. Review `mount_checks` in config file
5. Temporarily remove `mount_checks` to bypass (not recommended for production)

### API Returns Empty Config

**Problem:** `/api/config` returns empty or minimal data.

**Solutions:**
1. Check if config module is available: `docker exec refresher python -c "from refresher.config import load_config"`
2. Review container logs: `docker logs refresher`
3. Verify Python dependencies are installed
4. Check for import errors in logs

## Integration Examples

### Python

```python
from refresher.config import load_config, route_for_path

config = load_config('/config/config.yaml')

# Get routing for a path
path = "/opt/media/jelly/tv/Show/Season 1/episode.mkv"
instance = route_for_path(path, config.routing)
print(f"Path {path} routes to {instance}")
```

### Shell Script

```bash
#!/bin/bash
# Get configuration via API
CONFIG=$(curl -s http://localhost:8088/api/config)
INTERVAL=$(echo "$CONFIG" | jq -r '.scan.interval')
echo "Scan interval: ${INTERVAL}s"
```

### JavaScript/React

```javascript
// Custom hook for config (see dashboard/src/hooks.js)
import { useConfig } from './hooks';

function ConfigDisplay() {
  const { config, loading, error } = useConfig();
  
  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  
  return (
    <div>
      <h2>Scan Roots</h2>
      <ul>
        {config.scan.roots.map((root, i) => 
          <li key={i}>{root}</li>
        )}
      </ul>
    </div>
  );
}
```

## Best Practices

1. **Keep sensitive data in environment variables**, not YAML files
2. **Use path mappings** to document container/host path relationships
3. **Order routing rules** from most specific to least specific
4. **Test configuration** using API endpoints before deploying
5. **Document custom routing** in your deployment notes
6. **Use mount checks** to prevent scans when mounts are unavailable
7. **Monitor the dashboard** for routing and configuration visibility

## See Also

- [Main README](README.md) - Quick start and overview
- [Database Schema](README_DB.md) - Database documentation
- [Dashboard Guide](README_DASHBOARD.md) - Dashboard setup
- [Manual Tools](README_MANUAL_TOOLS.md) - Manual repair tools
