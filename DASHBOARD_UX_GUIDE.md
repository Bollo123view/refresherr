# Dashboard UX Guide: Configuration & Routing Visibility

This guide demonstrates how configuration, routing, and path mapping information is displayed in the Refresherr dashboard for troubleshooting and monitoring.

## Overview

The dashboard provides real-time visibility into:
- System configuration (scan roots, intervals, settings)
- Path routing rules (which paths route to which instances)
- Path mappings (container ↔ host path translation)
- Symlink health statistics
- Practical routing examples for troubleshooting

## Dashboard Sections

### 1. Symlink Health Statistics

**Purpose:** Monitor the overall health of your media library symlinks.

**What You'll See:**
```
┌─────────────────────────────────────────────────────┐
│ Symlink Health Statistics              [Refresh]   │
├─────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ Total        │  │ Healthy      │  │ Broken   │ │
│  │ Symlinks     │  │              │  │          │ │
│  │    1,234     │  │    1,198     │  │    36    │ │
│  │ 97.1% healthy│  │ Working      │  │ Repair   │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐               │
│  │ Movies       │  │ Episodes     │               │
│  │ 456 / 500    │  │ 742 / 750    │               │
│  │ 91.2% linked │  │ 98.9% linked │               │
│  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────┘
```

**Use Case:** Quick health check at a glance. Broken count alerts you to issues.

### 2. Configuration Display

**Purpose:** View current operational configuration for verification and debugging.

**What You'll See:**
```
┌─────────────────────────────────────────────────────┐
│ Configuration                                        │
├─────────────────────────────────────────────────────┤
│ Scan Roots:                   Scan Interval: 300s  │
│ • /opt/media/jelly/tv         Dry Run Mode: Yes    │
│ • /opt/media/jelly/hayu                             │
│ • /opt/media/jelly/4k         Relay Configured: Yes│
│ • /opt/media/jelly/movies                           │
└─────────────────────────────────────────────────────┘
```

**Use Cases:**
- Verify scan roots are correct
- Confirm dry run mode status before enabling repairs
- Check if relay service is configured
- Validate scan interval matches expectations

### 3. Path Routing & Mapping

**Purpose:** Understand how paths are routed to different Sonarr/Radarr instances and how container/host path translation works.

#### 3a. Route Configuration Table

**What You'll See:**
```
┌─────────────────────────────────────────────────────┐
│ Path Routing & Mapping                              │
├─────────────────────────────────────────────────────┤
│ Route Configuration                                  │
│ ┌──────────────────────────────┬─────────────────┐ │
│ │ Path Prefix                  │ Routes To       │ │
│ ├──────────────────────────────┼─────────────────┤ │
│ │ /opt/media/jelly/hayu        │ sonarr_hayu     │ │
│ │ /opt/media/jelly/4k          │ radarr_4k       │ │
│ │ /opt/media/jelly/doc         │ radarr_doc      │ │
│ │ /opt/media/jelly/movies      │ radarr_movie    │ │
│ │ /opt/media/jelly/tv          │ sonarr_tv       │ │
│ └──────────────────────────────┴─────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**Use Cases:**
- Verify routing rules match your directory structure
- Debug why a symlink routed to the wrong instance
- Understand the precedence of routing rules
- Confirm all your media roots have corresponding routes

#### 3b. Path Mappings Table

**What You'll See:**
```
┌───────────────────────────────────────────────────────────────────────┐
│ Path Mappings (Container ↔ Host)                                     │
├───────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────┬─────────────────────┬─────────────────────────┐│
│ │ Container Path   │ Host/Logical Path   │ Description             ││
│ ├──────────────────┼─────────────────────┼─────────────────────────┤│
│ │ /opt/media/jelly │ /mnt/storage/media/ │ Jellyfin symlink root   ││
│ │                  │ jelly               │                         ││
│ │ /mnt/remote/     │ /mnt/cloud/         │ RealDebrid rclone mount ││
│ │ realdebrid       │ realdebrid-mount    │                         ││
│ │ /data            │ /opt/refresherr/    │ Refresherr data dir     ││
│ │                  │ data                │ (database, logs)        ││
│ └──────────────────┴─────────────────────┴─────────────────────────┘│
└───────────────────────────────────────────────────────────────────────┘
```

**Use Cases:**
- Understand the relationship between container and host paths
- Debug path-related issues when reading logs
- Verify Docker volume mounts match your configuration
- Share correct paths with external tools or scripts

#### 3c. Routing Examples

**What You'll See:**
```
┌─────────────────────────────────────────────────────────────────────┐
│ Routing Examples                                                    │
├─────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ Path: /opt/media/jelly/hayu/Show Name/Season 1/episode.mkv     ││
│ │ Routes to: sonarr_hayu                                          ││
│ │ Content under /opt/media/jelly/hayu routes to sonarr_hayu      ││
│ └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ Path: /opt/media/jelly/4k/Movie (2023)/movie.mkv               ││
│ │ Routes to: radarr_4k                                            ││
│ │ Content under /opt/media/jelly/4k routes to radarr_4k          ││
│ └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────────┐│
│ │ Path: /opt/media/jelly/tv/Show/Season 1/episode.mkv            ││
│ │ Routes to: sonarr_tv                                            ││
│ │ Content under /opt/media/jelly/tv routes to sonarr_tv          ││
│ └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

**Use Cases:**
- See concrete examples of how routing works
- Copy example paths for testing
- Understand what instance will handle specific paths
- Verify routing logic with real-world examples

## Troubleshooting Workflows

### Scenario 1: Symlink Routes to Wrong Instance

**Problem:** A broken symlink in `/opt/media/jelly/4k/` is being repaired by `radarr_movie` instead of `radarr_4k`.

**Troubleshooting Steps:**

1. **Check Dashboard Routing Table**
   - Navigate to dashboard
   - Scroll to "Path Routing & Mapping" section
   - Look at "Route Configuration" table
   - Verify `/opt/media/jelly/4k` is listed with `radarr_4k`

2. **Check Route Ordering**
   - Routes are matched longest-prefix-first
   - Ensure `/opt/media/jelly/4k` comes before `/opt/media/jelly/`
   - If not, update `config.yaml` routing order

3. **Verify Config Loading**
   - Check "Configuration" section shows correct roots
   - Confirm scan roots include the path in question
   - Restart service if config changes were made

4. **Test with API**
   ```bash
   curl http://localhost:8088/api/routes | jq '.routing'
   ```

### Scenario 2: Path Confusion Between Container and Host

**Problem:** Logs reference `/opt/media/jelly/...` but you don't see that path on your host system.

**Troubleshooting Steps:**

1. **Check Path Mappings Table**
   - Navigate to "Path Routing & Mapping" section
   - Find "Path Mappings (Container ↔ Host)" table
   - Locate the container path: `/opt/media/jelly`
   - Note the corresponding host path (e.g., `/mnt/storage/media/jelly`)

2. **Understand the Translation**
   - Container sees: `/opt/media/jelly/tv/Show/file.mkv`
   - Host actually has: `/mnt/storage/media/jelly/tv/Show/file.mkv`
   - Docker volume mount: `/mnt/storage/media/jelly:/opt/media/jelly`

3. **Verify Volume Mounts**
   ```bash
   docker inspect refresher | jq '.[0].Mounts'
   ```

4. **Check Description Field**
   - Read the description in the mapping table
   - This explains what each path represents
   - Helps identify which mount corresponds to which service

### Scenario 3: Configuration Not Taking Effect

**Problem:** Changed `config.yaml` but dashboard still shows old values.

**Troubleshooting Steps:**

1. **Verify File Location**
   - Check "Configuration" section in dashboard
   - Ensure CONFIG_FILE env var points to correct file
   - Default: `/config/config.yaml`

2. **Check YAML Syntax**
   ```bash
   python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
   ```

3. **Restart Services**
   ```bash
   docker-compose restart refresher dashboard
   ```

4. **Check API Response**
   ```bash
   curl http://localhost:8088/api/config | jq
   ```

5. **Review Logs**
   ```bash
   docker logs refresher
   ```

## API Endpoints for Programmatic Access

All dashboard information is also available via API:

### `/api/config`
Returns complete configuration including scan settings, relay config, and runtime options.

**Example:**
```bash
curl http://localhost:8088/api/config | jq '.scan.roots'
```

### `/api/routes`
Returns routing and path mapping configuration with examples.

**Example:**
```bash
curl http://localhost:8088/api/routes | jq '.path_mappings'
```

### `/api/stats`
Returns current symlink health statistics.

**Example:**
```bash
curl http://localhost:8088/api/stats | jq '.symlinks.broken'
```

## Best Practices

1. **Regular Dashboard Checks**
   - Monitor broken count daily
   - Verify dry run mode status before enabling repairs
   - Check routing examples match your expectations

2. **Document Your Setup**
   - Use description fields in path_mappings
   - Keep comments in config.yaml up to date
   - Share routing table screenshot with team members

3. **Test Routing Changes**
   - Use routing examples to verify behavior
   - Check API endpoints after config changes
   - Test with a dry run first

4. **Leverage Path Mappings**
   - Document all Docker volume mounts
   - Use consistent naming conventions
   - Include both container and host paths in documentation

## Future Enhancements

Planned dashboard features:
- [ ] Real-time scan progress indicator
- [ ] Interactive routing rule tester
- [ ] Path translation calculator (container ↔ host)
- [ ] Historical broken symlink trends
- [ ] Per-instance repair success rates
- [ ] Configuration validation warnings
- [ ] One-click config export/import

## See Also

- [Dashboard Setup](README_DASHBOARD.md)
- [Configuration Guide](README_CONFIG.md)
- [Troubleshooting](README.md#troubleshooting)
- [API Documentation](README.md#api-endpoints)
