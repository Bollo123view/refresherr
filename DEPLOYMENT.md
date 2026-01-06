# Deployment Guide

This guide covers deployment options for Refresherr, including the current multi-container setup and the future unified backend approach.

## Table of Contents

1. [Current Architecture](#current-architecture)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Building the Dashboard](#building-the-dashboard)
5. [Future: Unified Backend](#future-unified-backend)
6. [Deployment Environments](#deployment-environments)
7. [Monitoring & Health Checks](#monitoring--health-checks)

## Current Architecture

Refresherr currently deploys as three separate services:

```
┌─────────────────────────────────────────────────────┐
│                  Docker Compose                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │  refresher   │  │  dashboard   │  │  relay   │ │
│  │  (scanner)   │  │  (API+UI)    │  │ (search) │ │
│  │              │  │              │  │          │ │
│  │ - Scans      │  │ - Flask API  │  │ - Sonarr │ │
│  │ - Detects    │  │ - React UI   │  │ - Radarr │ │
│  │ - Enqueues   │  │ - SQLite DB  │  │   proxy  │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
│         │                  │                │      │
│         └──────────────────┴────────────────┘      │
│              Shared: config/, data/                │
└─────────────────────────────────────────────────────┘
```

### Services

1. **refresher** - Background scanner
   - Monitors symlink roots for broken links
   - Records status in SQLite database
   - Enqueues repair actions via relay service
   - Uses centralized config from `/config/config.yaml`

2. **dashboard** - Web UI and API
   - Flask backend serving REST API
   - Exposes `/api/config`, `/api/routes`, `/api/stats`
   - React frontend (development mode or built static assets)
   - SQLite database access for queries

3. **research-relay** - Search proxy
   - Handles Sonarr/Radarr search requests
   - Routes to correct instance based on type
   - Provides "Find" functionality for broken symlinks

## Quick Start

### 1. Copy Sample Configuration

```bash
# Copy environment variables template
cp config/env.sample .env

# Copy YAML configuration template
cp config/config.sample.yaml config/config.yaml

# Edit both files for your environment
nano .env
nano config/config.yaml
```

### 2. Configure Your Setup

Key settings to customize:

**In `.env`:**
```bash
DRYRUN=true                              # Set to false to enable repairs
RELAY_BASE=http://relay:5050             # Relay service URL
RELAY_TOKEN=REPLACE-WITH-YOUR-SECRET-TOKEN  # Secret token for relay
DISCORD_WEBHOOK=https://...              # Optional Discord notifications
```

**In `config/config.yaml`:**
```yaml
scan:
  roots:
    - /opt/media/jelly/tv      # Your media directories
    - /opt/media/jelly/movies
  
routing:
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv             # Must match relay config
  - prefix: /opt/media/jelly/movies
    type: radarr_movie

path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media # Host path for troubleshooting
    description: "Main library"
```

### 3. Configure Docker Volumes

Update `docker-compose.yml` volumes to match your system:

```yaml
volumes:
  # Configuration files (read-only)
  - ./config:/config:ro
  
  # Data directory (database, logs)
  - ./data:/data
  
  # Symlink root (read-write for repairs)
  - /your/media/path:/opt/media/jelly:rw
  
  # Actual file storage (read-only)
  - /your/realdebrid/mount:/mnt/remote/realdebrid:ro
```

**Important:** The left side is the **host path**, the right side is the **container path**. Document these relationships in your `path_mappings` configuration.

### 4. Start Services

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check health
docker-compose ps
curl http://localhost:8088/health
```

### 5. Access Dashboard

Open http://localhost:8088 in your browser to:
- View symlink health statistics
- Check configuration and routing
- See path mappings
- Monitor broken symlinks

## Configuration

See [README_CONFIG.md](README_CONFIG.md) for detailed configuration documentation.

### Configuration Precedence

Settings are applied in this order (later overrides earlier):

1. Built-in defaults in `config.py`
2. YAML file (`config/config.yaml`)
3. Environment variables (`.env`)

### Key Configuration Sections

#### Scan Configuration
```yaml
scan:
  roots: [...]              # Directories to scan
  mount_checks: [...]       # Mounts to verify before scanning
  interval: 300             # Scan interval (seconds)
  ignore_patterns: [...]    # Patterns to skip
```

#### Routing Configuration
```yaml
routing:
  - prefix: /path/to/media
    type: sonarr_tv         # Instance identifier
```

Routes are matched **longest-prefix-first** automatically.

#### Path Mappings
```yaml
path_mappings:
  - container: /opt/media
    logical: /mnt/storage/media
    description: "..."
```

Used for container ↔ host path translation in logs and API responses.

## Building the Dashboard

The React dashboard can be built for production and served as static assets:

```bash
cd dashboard

# Install dependencies
npm install

# Build for production
npm run build

# Output is in dashboard/build/
```

### Serving Built Assets

The dashboard service is prepared to serve built React assets:

1. Build the dashboard (see above)
2. Copy `dashboard/build/` to `services/dashboard/static/`
3. Update Flask app to serve from `/static` route
4. Restart dashboard service

**Future Enhancement:** This will be automated in the unified backend container.

## Future: Unified Backend

### Planned Architecture

```
┌─────────────────────────────────────────┐
│       Unified Backend Container         │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────────────┐  │
│  │     FastAPI / Flask Backend      │  │
│  │                                  │  │
│  │  • REST API (/api/*)             │  │
│  │  • Static files (/static)        │  │
│  │  • Metrics & monitoring          │  │
│  └──────────────────────────────────┘  │
│                │                        │
│  ┌─────────────┴────────────┐          │
│  │                          │          │
│  ▼                          ▼          │
│  ┌──────────┐        ┌──────────────┐ │
│  │ Scanner  │        │   SQLite     │ │
│  │ (async)  │────────│   Database   │ │
│  └──────────┘        └──────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

### Benefits

- **Simplified deployment** - Single container to manage
- **Resource efficiency** - Shared Python process
- **Better performance** - No inter-container communication
- **Easier development** - Single codebase, unified logging

### Migration Path

To prepare for the unified backend:

1. ✅ Centralized config module (`config.py`) - **Done**
2. ✅ API endpoints structured for static serving - **Done**
3. ✅ Dashboard builds to `build/` directory - **Done**
4. ✅ Path mapping support throughout - **Done**
5. 🔲 Serve static React assets from Flask
6. 🔲 Background scanner as async task
7. 🔲 Single Dockerfile with both scanner and API
8. 🔲 Update docker-compose to use unified service

## Deployment Environments

### Development

```bash
# Terminal 1: Scanner (watches for changes)
cd app
python -m refresher.cli run

# Terminal 2: API backend
cd services/dashboard
python app.py

# Terminal 3: React dev server (hot reload)
cd dashboard
npm start
```

Access at:
- React dev server: http://localhost:3000 (proxies API calls)
- Flask API: http://localhost:8088

### Production (Current)

```bash
# Build and start all services
docker-compose up -d --build

# View logs
docker-compose logs -f

# Update config without restart (most changes)
# Edit config/config.yaml
# Restart to apply
docker-compose restart refresher dashboard
```

### Production (Future Unified)

```bash
# Build unified container
docker build -t refresherr:latest .

# Run unified container
docker run -d \
  -v ./config:/config:ro \
  -v ./data:/data \
  -v /opt/media:/opt/media:rw \
  -p 8088:8088 \
  refresherr:latest
```

## Monitoring & Health Checks

### Health Check Endpoints

```bash
# Dashboard health
curl http://localhost:8088/health

# Configuration status
curl http://localhost:8088/api/config

# Routing status
curl http://localhost:8088/api/routes

# Statistics
curl http://localhost:8088/api/stats
```

### Docker Health Checks

Services include built-in health checks:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8088/health"]
  interval: 30s
  timeout: 5s
  retries: 5
```

Check status:
```bash
docker-compose ps
# Look for "(healthy)" status
```

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f refresher
docker-compose logs -f dashboard

# Last 100 lines
docker-compose logs --tail=100 refresher
```

### Common Issues

#### Config Not Loading
```bash
# Verify config file path
docker exec refresher env | grep CONFIG_FILE

# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"

# Verify volume mount
docker exec refresher ls -la /config/
```

#### Wrong Routing
```bash
# Check routing via API
curl http://localhost:8088/api/routes | jq '.routing'

# Verify path prefixes match your structure
```

#### Mount Issues
```bash
# Verify mounts inside container
docker exec refresher ls -la /mnt/remote/realdebrid
docker exec refresher df -h
```

## Performance Tuning

### Scan Interval

Adjust based on your needs:
```bash
# Fast scanning (more CPU, quicker detection)
SCAN_INTERVAL=60

# Standard scanning (balanced)
SCAN_INTERVAL=300

# Slow scanning (less CPU, delayed detection)
SCAN_INTERVAL=900
```

### Database Optimization

SQLite performs well for most deployments. For very large libraries:
```yaml
database:
  # Increase cache size (in KB)
  cache_size: 10000
  
  # Enable write-ahead logging
  journal_mode: WAL
```

### Resource Limits

Add to `docker-compose.yml`:
```yaml
services:
  refresher:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          memory: 256M
```

## Backup & Restore

### Backup Configuration

```bash
# Backup config and database
tar -czf refresherr-backup-$(date +%Y%m%d).tar.gz \
  config/ data/symlinks.db
```

### Restore

```bash
# Extract backup
tar -xzf refresherr-backup-20240106.tar.gz

# Restart services
docker-compose restart
```

## Security Considerations

1. **Secrets Management**
   - Store sensitive data in `.env` file (gitignored)
   - Use Docker secrets in production
   - Rotate tokens periodically

2. **Volume Permissions**
   - Mount config as read-only (`:ro`)
   - Restrict writable mounts to necessary directories
   - Use least-privilege principle

3. **Network Security**
   - Reverse proxy for HTTPS (Caddy, Nginx)
   - Firewall rules for port 8088
   - Internal Docker network for service communication

## Troubleshooting

See [README.md](README.md#troubleshooting) and [README_CONFIG.md](README_CONFIG.md#troubleshooting) for detailed troubleshooting guides.

Quick checks:
```bash
# Service status
docker-compose ps

# Recent logs
docker-compose logs --tail=50

# Config validation
curl http://localhost:8088/api/config | jq

# Database check
curl http://localhost:8088/dbcheck | jq
```

## Support & Documentation

- [Main README](README.md) - Overview and quick start
- [Configuration Guide](README_CONFIG.md) - Detailed config documentation
- [Dashboard UX Guide](DASHBOARD_UX_GUIDE.md) - Dashboard usage examples
- [Database Documentation](README_DB.md) - Schema and operations
- [Usage Examples](USAGE_EXAMPLES.md) - Common workflows

## Contributing

When developing new features:
1. Update configuration schema if adding new options
2. Document changes in README files
3. Add API endpoints for UI visibility
4. Include examples in sample config files
5. Test with both YAML and environment configuration
