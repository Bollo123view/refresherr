# Semantic Deployment Guide

This guide explains how to deploy Refresherr using environment-specific configurations for development, staging, and production environments.

## Overview

Refresherr supports semantic deployment through environment-specific configuration files that allow you to maintain different settings for different deployment targets while keeping your deployment process consistent.

## Configuration Files

### Available Configurations

- **`config.sample.yaml`**: Comprehensive example with all options documented
- **`config.dev.yaml`**: Development environment configuration
- **`config.prod.yaml`**: Production environment configuration

### Configuration Precedence

Configuration is loaded with the following precedence (highest to lowest):

1. **Environment Variables**: Override any config file setting
2. **Config File** (YAML): Specified via `CONFIG_FILE` environment variable
3. **Default Values**: Built-in defaults

## Development Deployment

### Quick Start

```bash
# Copy development config
cp config/config.dev.yaml config/config.yaml

# Create .env file for development
cat > .env << EOF
# Development settings
DRYRUN=true
SCAN_INTERVAL=30
DATA_DIR=/data

# Relay (local development)
RELAY_BASE=http://localhost:5050
RELAY_TOKEN=dev-token-change-me

# ARR instances (optional for dev)
SONARR_TV_URL=http://localhost:8989
SONARR_TV_API=your-dev-api-key

RADARR_MOVIE_URL=http://localhost:7878
RADARR_MOVIE_API=your-dev-api-key
EOF

# Run with Docker Compose
docker-compose up
```

### Development Configuration Features

- **Short scan intervals** (30 seconds) for rapid testing
- **Test directories** instead of production paths
- **Notifications disabled** to avoid spam
- **No mount checks** for easier local development
- **Dry-run enabled** by default

### Development Best Practices

1. Use test media directories, not production paths
2. Keep `DRYRUN=true` until ready to test repairs
3. Use local/mock instances of Sonarr/Radarr
4. Enable verbose logging for debugging

## Production Deployment

### Prerequisites

Before deploying to production:

1. ✅ Test configuration in development environment
2. ✅ Verify all mount points are accessible
3. ✅ Configure Sonarr/Radarr API keys
4. ✅ Set up Discord notifications (optional)
5. ✅ Plan backup strategy for `/data` directory
6. ✅ Review and test routing configuration

### Production Setup

```bash
# Copy production config
cp config/config.prod.yaml config/config.yaml

# Create secure .env file
cat > .env << EOF
# Production settings
DRYRUN=true  # Start in dry-run, switch to false after testing
SCAN_INTERVAL=300
DATA_DIR=/data

# Relay service
RELAY_BASE=http://localhost:5050
RELAY_TOKEN=$(openssl rand -hex 32)

# Sonarr instances
SONARR_TV_URL=http://sonarr-tv:8989
SONARR_TV_API=your-production-sonarr-api-key

# Radarr instances
RADARR_MOVIE_URL=http://radarr:7878
RADARR_MOVIE_API=your-production-radarr-api-key

RADARR_4K_URL=http://radarr-4k:7878
RADARR_4K_API=your-production-4k-api-key

# CineSync configuration
CINESYNC_BASE=/opt/media/jelly/cinesync/CineSync
CINESYNC_REPAIR_ROOTS=/opt/media/jelly/tv,/opt/media/jelly/movies
CINESYNC_DRY_RUN=1
CINESYNC_LIMIT=200
CINESYNC_ALLOWED_TARGET_PREFIXES=/mnt/remote

# Notifications
DISCORD_WEBHOOK=https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE

# Flask secret for dashboard sessions
FLASK_SECRET=$(openssl rand -hex 32)
EOF

# Secure the .env file
chmod 600 .env
```

### Docker Compose Configuration

Update `docker-compose.yml` for production:

```yaml
version: '3.8'

services:
  refresherr:
    image: ghcr.io/bollo123view/refresherr:latest
    container_name: refresherr
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      # Configuration (read-only)
      - ./config:/config:ro
      
      # Data directory (read-write)
      - ./data:/data
      
      # Media directories (adjust paths for your system)
      - /mnt/storage/media/jellyfin:/opt/media/jelly:rw
      - /mnt/cloud-mounts/realdebrid:/mnt/remote/realdebrid:ro
    ports:
      - "8088:8088"
    networks:
      - media-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8088/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

networks:
  media-network:
    external: true
```

### Production Deployment Steps

1. **Deploy in dry-run mode first**:
   ```bash
   # Ensure DRYRUN=true in .env
   docker-compose up -d
   ```

2. **Monitor initial scans**:
   ```bash
   # Watch logs
   docker-compose logs -f refresherr
   
   # Check dashboard
   open http://localhost:8088
   ```

3. **Verify configuration**:
   ```bash
   # Check configuration endpoint
   curl http://localhost:8088/api/config | jq
   
   # Check routing
   curl http://localhost:8088/api/routes | jq
   
   # Check stats
   curl http://localhost:8088/api/stats | jq
   ```

4. **Review dry-run manifest**:
   ```bash
   # Check what would be repaired
   curl http://localhost:8088/api/manifest | jq
   ```

5. **Enable repairs when ready**:
   ```bash
   # Update .env
   sed -i 's/DRYRUN=true/DRYRUN=false/' .env
   
   # Restart container
   docker-compose restart refresherr
   ```

### Production Configuration Features

- **Standard scan interval** (300 seconds)
- **Production media paths** with proper mount checks
- **Path mappings** for container ↔ host translation
- **Multiple ARR instances** with routing by path
- **Notifications enabled** for repair events
- **CineSync configuration** for hotswap repairs

## Staging Deployment

For staging environments, create a `config.staging.yaml`:

```yaml
# Inherit from production config but with:
# - Separate media paths for testing
# - Notifications to different channel
# - Shorter intervals for faster feedback
```

## Environment-Specific Settings

### Environment Variables by Environment

| Variable | Development | Production |
|----------|-------------|------------|
| `DRYRUN` | `true` | `true` → `false` |
| `SCAN_INTERVAL` | `30` | `300` |
| `CINESYNC_DRY_RUN` | `1` | `1` → `0` |
| Notifications | Disabled | Enabled |
| Mount Checks | None | Required |

## Updating Configuration

### Updating Existing Deployment

```bash
# 1. Update config file
vim config/config.yaml

# 2. Validate configuration
python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"

# 3. Restart container to apply changes
docker-compose restart refresherr

# 4. Verify changes
curl http://localhost:8088/api/config | jq
```

### Hot Reload (Limited)

Some settings can be changed via API without restart:

```bash
# Toggle dry-run mode
curl -X POST http://localhost:8088/api/config/dryrun \
  -H "Content-Type: application/json" \
  -d '{"dryrun": false}'

# Toggle orchestrator
curl -X POST http://localhost:8088/api/orchestrator/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

## Backup and Recovery

### Backup Strategy

```bash
# Backup data directory (includes database)
tar -czf refresherr-backup-$(date +%Y%m%d).tar.gz data/

# Backup configuration
tar -czf refresherr-config-$(date +%Y%m%d).tar.gz config/ .env
```

### Recovery

```bash
# Restore data
tar -xzf refresherr-backup-YYYYMMDD.tar.gz

# Restore configuration
tar -xzf refresherr-config-YYYYMMDD.tar.gz

# Restart services
docker-compose restart refresherr
```

## Monitoring

### Health Checks

```bash
# Container health
docker ps | grep refresherr

# Application health
curl http://localhost:8088/health

# Stats
curl http://localhost:8088/api/stats
```

### Logs

```bash
# Follow logs
docker-compose logs -f refresherr

# Last 100 lines
docker-compose logs --tail=100 refresherr

# Search logs
docker-compose logs refresherr | grep ERROR
```

## Troubleshooting

### Configuration Not Loading

```bash
# Check config file syntax
python -c "import yaml; print(yaml.safe_load(open('config/config.yaml')))"

# Check environment variables
docker-compose exec refresherr env | grep -E "(DRYRUN|CONFIG|SCAN)"

# Check config loading in logs
docker-compose logs refresherr | grep -i config
```

### Mount Issues

```bash
# Verify mounts inside container
docker-compose exec refresherr ls -la /opt/media/jelly
docker-compose exec refresherr ls -la /mnt/remote/realdebrid

# Check mount points in config
curl http://localhost:8088/api/config | jq '.scan.mount_checks'
```

### Routing Issues

```bash
# Check routing configuration
curl http://localhost:8088/api/routes | jq

# Test path routing
curl "http://localhost:8088/api/routes?path=/opt/media/jelly/movies/Test" | jq
```

## Security Considerations

1. **Secrets Management**:
   - Never commit `.env` files
   - Use strong random tokens
   - Rotate tokens periodically

2. **Network Security**:
   - Use reverse proxy with TLS for external access
   - Restrict dashboard access by IP if possible
   - Keep relay service internal-only

3. **File System Permissions**:
   - Use read-only mounts for source files
   - Limit write access to necessary directories
   - Run container as non-root user (future enhancement)

4. **Updates**:
   - Review changelog before updating
   - Test updates in staging first
   - Keep backups before major updates

## Migration Between Environments

### Dev → Production

1. Export tested configuration
2. Update paths for production environment
3. Replace test API keys with production keys
4. Enable mount checks
5. Configure notifications
6. Deploy with dry-run enabled
7. Test thoroughly
8. Disable dry-run

## Support

For deployment assistance:

- [GitHub Issues](https://github.com/Bollo123view/refresherr/issues)
- [GitHub Discussions](https://github.com/Bollo123view/refresherr/discussions)
- See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup

## Additional Resources

- [Main README](README.md) - Complete documentation
- [Configuration Sample](config/config.sample.yaml) - Full configuration reference
- [Contributing Guide](CONTRIBUTING.md) - Development guidelines
