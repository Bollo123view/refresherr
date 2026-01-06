# Usage Examples

This document provides practical examples of using Refresherr's configuration system and API endpoints.

## Table of Contents

1. [Configuration Examples](#configuration-examples)
2. [API Usage Examples](#api-usage-examples)
3. [Python Integration](#python-integration)
4. [Shell Script Integration](#shell-script-integration)
5. [React/JavaScript Integration](#reactjavascript-integration)

## Configuration Examples

### Basic Configuration

Minimal setup for a single media library:

```yaml
# config/config.yaml
scan:
  roots:
    - /opt/media/jelly/tv
  interval: 300

routing:
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv

relay:
  base_env: RELAY_BASE
  token_env: RELAY_TOKEN
```

### Multi-Instance Configuration

Configuration for multiple Sonarr/Radarr instances:

```yaml
scan:
  roots:
    - /opt/media/jelly/tv
    - /opt/media/jelly/anime
    - /opt/media/jelly/4k
    - /opt/media/jelly/movies
  
  mount_checks:
    - /mnt/remote/realdebrid
  
  interval: 300

routing:
  # More specific paths first
  - prefix: /opt/media/jelly/anime
    type: sonarr_anime
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv
  - prefix: /opt/media/jelly/4k
    type: radarr_4k
  - prefix: /opt/media/jelly/movies
    type: radarr_movie

path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Jellyfin library"
  
  - container: /mnt/remote/realdebrid
    logical: /mnt/cloud/rd-mount
    description: "RealDebrid mount"
```

### Complex Path Rewriting

Configuration with path rewrites for multi-mount scenarios:

```yaml
scan:
  roots:
    - /opt/media/jelly/tv
  
  rewrites:
    # Rewrite old mount paths to new ones
    - from: /mnt/old-mount/realdebrid
      to: /mnt/remote/realdebrid
    
    # Rewrite cloud provider paths
    - from: /mnt/cloud1/data
      to: /mnt/unified/data
  
  mount_checks:
    - /mnt/remote/realdebrid
    - /mnt/unified/data

routing:
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv
```

## API Usage Examples

### Check Configuration

View current configuration:

```bash
curl http://localhost:8088/api/config | jq
```

View only routing configuration:

```bash
curl http://localhost:8088/api/config | jq '.routing'
```

### View Routing Examples

Get routing configuration with practical examples:

```bash
curl http://localhost:8088/api/routes | jq '.examples'
```

Expected output:
```json
[
  {
    "path": "/opt/media/jelly/tv/Example Show/Season 1/episode.mkv",
    "routes_to": "sonarr_tv",
    "description": "Content under /opt/media/jelly/tv routes to sonarr_tv"
  }
]
```

### Check Symlink Statistics

Get overall health statistics:

```bash
curl http://localhost:8088/api/stats | jq
```

Expected output:
```json
{
  "movies": {
    "linked": 150,
    "total": 200,
    "percentage": 75.0
  },
  "episodes": {
    "linked": 5000,
    "total": 5500,
    "percentage": 90.9
  },
  "symlinks": {
    "total": 5150,
    "ok": 5100,
    "broken": 50,
    "percentage_healthy": 99.0
  }
}
```

### List Broken Symlinks

Get all broken symlinks:

```bash
curl http://localhost:8088/api/broken | jq
```

Filter broken symlinks by keyword:

```bash
curl http://localhost:8088/api/broken | jq '.[] | select(.title | contains("Breaking Bad"))'
```

## Python Integration

### Load and Use Configuration

```python
from refresher.config import load_config, route_for_path, container_to_logical

# Load configuration
config = load_config('/config/config.yaml')

# Print scan roots
print("Scan roots:")
for root in config.scan.roots:
    print(f"  - {root}")

# Check routing for a path
path = "/opt/media/jelly/tv/Show/Season 1/episode.mkv"
instance = route_for_path(path, config.routing)
print(f"\nPath {path}")
print(f"Routes to: {instance}")

# Translate paths
logical = container_to_logical(path, config.path_mappings)
print(f"Logical path: {logical}")
```

### Use in Scanner

```python
from refresher.config import load_config
from refresher.core.scanner import scan_once

# Load config and run scan
config = load_config()
result = scan_once(config, dryrun=True)

# Process results
if result['ok']:
    summary = result['summary']
    print(f"Examined: {summary['examined']}")
    print(f"Broken: {summary['broken_count']}")
else:
    print(f"Scan failed: {result['summary'].get('error')}")
```

### Custom Path Router

```python
from refresher.config import load_config, route_for_path

config = load_config()

def get_instance_for_file(file_path: str) -> str:
    """Determine which Sonarr/Radarr instance should handle this file."""
    instance = route_for_path(file_path, config.routing)
    if instance:
        return instance
    
    # Fallback logic
    if '/tv/' in file_path or '/shows/' in file_path:
        return 'sonarr_default'
    else:
        return 'radarr_default'

# Example usage
paths = [
    "/opt/media/jelly/tv/Show/file.mkv",
    "/opt/media/jelly/4k/Movie/file.mkv",
    "/opt/media/other/random.mkv"
]

for path in paths:
    instance = get_instance_for_file(path)
    print(f"{path} -> {instance}")
```

## Shell Script Integration

### Configuration Validation Script

```bash
#!/bin/bash
# validate_config.sh - Validate Refresherr configuration

CONFIG_URL="http://localhost:8088/api/config"
ROUTES_URL="http://localhost:8088/api/routes"

echo "=== Validating Refresherr Configuration ==="

# Check if API is accessible
if ! curl -sf "$CONFIG_URL" > /dev/null; then
    echo "❌ Cannot reach API at $CONFIG_URL"
    exit 1
fi
echo "✅ API is accessible"

# Get configuration
CONFIG=$(curl -s "$CONFIG_URL")

# Check scan roots
ROOTS=$(echo "$CONFIG" | jq -r '.scan.roots[]' 2>/dev/null)
ROOT_COUNT=$(echo "$CONFIG" | jq -r '.scan.roots | length' 2>/dev/null)
echo "✅ Found $ROOT_COUNT scan roots"

# Check routing
ROUTE_COUNT=$(echo "$CONFIG" | jq -r '.routing | length' 2>/dev/null)
echo "✅ Found $ROUTE_COUNT routing rules"

# Check path mappings
MAPPING_COUNT=$(echo "$CONFIG" | jq -r '.path_mappings | length' 2>/dev/null)
echo "✅ Found $MAPPING_COUNT path mappings"

# Check relay configuration
TOKEN_SET=$(echo "$CONFIG" | jq -r '.relay.token_set' 2>/dev/null)
if [ "$TOKEN_SET" = "true" ]; then
    echo "✅ Relay token is configured"
else
    echo "⚠️  Relay token not set"
fi

echo ""
echo "=== Routing Examples ==="
curl -s "$ROUTES_URL" | jq -r '.examples[] | "  \(.path)\n    → \(.routes_to)"'

echo ""
echo "✅ Configuration validation complete"
```

### Health Monitoring Script

```bash
#!/bin/bash
# monitor_health.sh - Monitor symlink health

STATS_URL="http://localhost:8088/api/stats"

while true; do
    STATS=$(curl -s "$STATS_URL")
    
    TOTAL=$(echo "$STATS" | jq -r '.symlinks.total')
    BROKEN=$(echo "$STATS" | jq -r '.symlinks.broken')
    HEALTHY_PCT=$(echo "$STATS" | jq -r '.symlinks.percentage_healthy')
    
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] Total: $TOTAL, Broken: $BROKEN, Health: ${HEALTHY_PCT}%"
    
    # Alert if health drops below threshold
    if (( $(echo "$HEALTHY_PCT < 95.0" | bc -l) )); then
        echo "⚠️  WARNING: Health below 95%!"
        # Send notification here
    fi
    
    sleep 60
done
```

## React/JavaScript Integration

### Configuration Display Component

```javascript
import React from 'react';
import { useConfig } from './hooks';

function ConfigDisplay() {
  const { config, loading, error } = useConfig();

  if (loading) return <div>Loading configuration...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!config) return null;

  return (
    <div className="config-display">
      <h2>Configuration</h2>
      
      <section>
        <h3>Scan Roots</h3>
        <ul>
          {config.scan.roots.map((root, i) => (
            <li key={i}><code>{root}</code></li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Routing</h3>
        <table>
          <thead>
            <tr>
              <th>Path Prefix</th>
              <th>Instance</th>
            </tr>
          </thead>
          <tbody>
            {config.routing.map((route, i) => (
              <tr key={i}>
                <td><code>{route.prefix}</code></td>
                <td><span className="badge">{route.type}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Settings</h3>
        <dl>
          <dt>Scan Interval</dt>
          <dd>{config.scan.interval}s</dd>
          
          <dt>Dry Run Mode</dt>
          <dd>{config.dryrun ? 'Yes' : 'No'}</dd>
          
          <dt>Log Level</dt>
          <dd>{config.log_level}</dd>
        </dl>
      </section>
    </div>
  );
}

export default ConfigDisplay;
```

### Routing Debugger Component

```javascript
import React, { useState } from 'react';
import { useRoutes } from './hooks';

function RoutingDebugger() {
  const { routes, loading, error } = useRoutes();
  const [testPath, setTestPath] = useState('');
  const [matchedRoute, setMatchedRoute] = useState(null);

  const handleTest = () => {
    if (!routes || !testPath) return;
    
    // Find matching route (longest prefix first)
    const match = routes.routing.find(r => 
      testPath.startsWith(r.prefix)
    );
    
    setMatchedRoute(match);
  };

  if (loading) return <div>Loading routes...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div className="routing-debugger">
      <h2>Routing Debugger</h2>
      
      <div className="test-input">
        <input
          type="text"
          value={testPath}
          onChange={(e) => setTestPath(e.target.value)}
          placeholder="/opt/media/jelly/tv/Show/file.mkv"
          style={{ width: '400px' }}
        />
        <button onClick={handleTest}>Test Route</button>
      </div>

      {matchedRoute && (
        <div className="result">
          <h3>Result</h3>
          <p>
            Path <code>{testPath}</code> routes to{' '}
            <span className="badge">{matchedRoute.type}</span>
          </p>
          <p>
            Matched prefix: <code>{matchedRoute.prefix}</code>
          </p>
        </div>
      )}

      {testPath && !matchedRoute && (
        <div className="result error">
          <p>⚠️ No matching route found for this path</p>
        </div>
      )}

      <div className="examples">
        <h3>Examples from Configuration</h3>
        {routes.examples?.map((example, i) => (
          <div key={i} className="example">
            <code>{example.path}</code> → {example.routes_to}
          </div>
        ))}
      </div>
    </div>
  );
}

export default RoutingDebugger;
```

### Stats Dashboard Component

```javascript
import React, { useEffect } from 'react';
import { useStats } from './hooks';

function StatsDashboard() {
  const { stats, loading, error, refresh } = useStats();

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (loading) return <div>Loading statistics...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!stats) return null;

  const healthColor = stats.symlinks.percentage_healthy >= 95 
    ? 'green' 
    : stats.symlinks.percentage_healthy >= 80 
    ? 'orange' 
    : 'red';

  return (
    <div className="stats-dashboard">
      <h2>Symlink Health</h2>
      
      <div className="stat-grid">
        <div className="stat-card">
          <h3>Total Symlinks</h3>
          <div className="value">{stats.symlinks.total}</div>
        </div>

        <div className={`stat-card ${healthColor}`}>
          <h3>Health</h3>
          <div className="value">
            {stats.symlinks.percentage_healthy}%
          </div>
          <div className="subtitle">
            {stats.symlinks.ok} OK / {stats.symlinks.broken} broken
          </div>
        </div>

        <div className="stat-card">
          <h3>Movies</h3>
          <div className="value">
            {stats.movies.linked} / {stats.movies.total}
          </div>
          <div className="subtitle">
            {stats.movies.percentage}% linked
          </div>
        </div>

        <div className="stat-card">
          <h3>Episodes</h3>
          <div className="value">
            {stats.episodes.linked} / {stats.episodes.total}
          </div>
          <div className="subtitle">
            {stats.episodes.percentage}% linked
          </div>
        </div>
      </div>

      <button onClick={refresh} className="refresh-btn">
        Refresh Stats
      </button>
    </div>
  );
}

export default StatsDashboard;
```

## Advanced Usage

### Custom Config Loader with Validation

```python
from refresher.config import load_config
import sys

def load_and_validate_config(config_path):
    """Load config with custom validation."""
    config = load_config(config_path)
    
    # Validation rules
    errors = []
    
    # Check scan roots exist
    import os
    for root in config.scan.roots:
        if not os.path.exists(root):
            errors.append(f"Scan root does not exist: {root}")
    
    # Check routing has at least one rule
    if not config.routing:
        errors.append("No routing rules defined")
    
    # Check relay is configured if needed
    if not config.relay.base_url and not config.relay.token:
        print("Warning: Relay not configured - auto-repair disabled")
    
    # Report errors
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  ❌ {error}")
        sys.exit(1)
    
    print("✅ Configuration valid")
    return config
```

### Path Mapping Helper

```python
from refresher.config import load_config, container_to_logical, logical_to_container

class PathMapper:
    """Helper class for path translation."""
    
    def __init__(self, config_path=None):
        self.config = load_config(config_path)
    
    def to_host(self, container_path: str) -> str:
        """Translate container path to host path."""
        return container_to_logical(container_path, self.config.path_mappings)
    
    def to_container(self, host_path: str) -> str:
        """Translate host path to container path."""
        return logical_to_container(host_path, self.config.path_mappings)
    
    def format_both(self, path: str) -> str:
        """Format path showing both container and host versions."""
        if path.startswith('/opt') or path.startswith('/mnt/remote'):
            # Assume container path
            host = self.to_host(path)
            return f"{path} (host: {host})"
        else:
            # Assume host path
            container = self.to_container(path)
            return f"{path} (container: {container})"

# Usage
mapper = PathMapper()
print(mapper.format_both("/opt/media/jelly/tv/Show/file.mkv"))
```

## See Also

- [Configuration Guide](README_CONFIG.md) - Detailed configuration documentation
- [Main README](README.md) - Quick start and overview
- [Dashboard Guide](README_DASHBOARD.md) - Dashboard setup and usage
