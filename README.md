# Refresher

Future-proof repair/refresh layer for RD/rclone media symlinks.
- Mount-aware scanner (dry-run by default)
- Discord notifications + one-click "Find" via relay
- SQLite history
- Dockerized, no cron needed
- **NEW**: Central configuration with path routing and container↔host mapping

## Quick Start

1. Copy the sample configuration:
   ```bash
   cp config/.env.sample .env
   cp config/config.yaml config/config.local.yaml
   ```

2. Edit `.env` and `config/config.yaml` to match your environment

3. Start the services:
   ```bash
   docker-compose up -d
   ```

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

See `config/.env.sample` for a complete list with descriptions.

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

### Mounting Volumes

When running Refresherr in Docker, ensure proper volume mounting:

```yaml
volumes:
  # Config files (read-only)
  - ./config:/config:ro
  
  # Data directory (read-write for database)
  - ./data:/data
  
  # Media symlink root (read-write)
  - /opt/media:/opt/media:rw
  
  # Actual file mount (read-only)
  - /opt/media/remote/realdebrid:/mnt/remote/realdebrid:ro
```

The left side of each volume mount is the **host path**, and the right side is the **container path**. Use path mappings in your config to document these relationships.

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

The React-based dashboard provides:
- Real-time symlink health statistics
- Configuration visibility
- Routing and path mapping display
- Troubleshooting examples

See [Dashboard Guide](README_DASHBOARD.md) for setup instructions.

### Building the Dashboard

```bash
cd dashboard
npm install
npm run build
```

The built static assets will be served by the backend at `/static` (future unified container).

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

## Documentation

- **[Configuration Guide](README_CONFIG.md)** - Detailed configuration documentation (you're reading it!)
- **[Database Schema](README_DB.md)** - Comprehensive database documentation including schema, tables, and operations
- [Ingest Guide](README_INGEST.md) - Media metadata ingestion from Sonarr/Radarr
- [Dashboard Guide](README_DASHBOARD.md) - Dashboard setup and usage
- [Manual Tools](README_MANUAL_TOOLS.md) - Manual repair tools and utilities
- [Replacement Guide](README_REPLACEMENT.md) - File replacement workflows
- [Apply Manual Mode](README_APPLY_MANUAL_MODE.md) - Manual application mode
