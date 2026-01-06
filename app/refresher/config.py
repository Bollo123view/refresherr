"""
Central configuration module for Refresherr.

This module provides a single source of configuration loading from:
- YAML configuration files
- Environment variables
- Defaults

Key features:
- Path routing and mapping (container <-> logical paths)
- Scan roots and mount checks
- Notification endpoints
- Relay configuration
- Database settings

The configuration supports explicit symlink path routing with both container (in-app)
and logical (host/out-of-app) paths for proper path translation in containerized environments.
"""

from __future__ import annotations
import os
import yaml
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class PathMapping:
    """Represents a path mapping between container and logical/host paths."""
    container_path: str
    logical_path: str
    description: str = ""

    def __post_init__(self):
        # Normalize paths (remove trailing slashes for consistency)
        self.container_path = self.container_path.rstrip("/")
        self.logical_path = self.logical_path.rstrip("/")


@dataclass
class RouteConfig:
    """Represents a routing configuration for path-based instance selection."""
    prefix: str
    type: str
    
    def __post_init__(self):
        self.prefix = self.prefix.rstrip("/")


@dataclass
class ScanConfig:
    """Scanner configuration."""
    roots: List[str] = field(default_factory=list)
    mount_checks: List[str] = field(default_factory=list)
    rewrites: List[Tuple[str, str]] = field(default_factory=list)
    interval: int = 300
    ignore_patterns: List[str] = field(default_factory=list)


@dataclass
class RelayConfig:
    """Relay service configuration."""
    base_url: str = ""
    token: str = ""
    base_env: str = "RELAY_BASE"
    token_env: str = "RELAY_TOKEN"
    
    def __post_init__(self):
        # Load from environment if not set
        if not self.base_url:
            self.base_url = os.environ.get(self.base_env, "")
        if not self.token:
            self.token = os.environ.get(self.token_env, "")


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = ""
    data_dir: str = "/data"
    
    def __post_init__(self):
        # Use environment variable or default
        self.data_dir = os.environ.get("DATA_DIR", self.data_dir)
        if not self.path:
            self.path = os.path.join(self.data_dir, "symlinks.db")


@dataclass
class NotificationConfig:
    """Notification configuration."""
    discord_webhook: str = ""
    enabled: bool = True
    
    def __post_init__(self):
        # Load from environment if not set
        if not self.discord_webhook:
            self.discord_webhook = os.environ.get("DISCORD_WEBHOOK", "")


@dataclass
class RefresherrConfig:
    """Main Refresherr configuration."""
    scan: ScanConfig = field(default_factory=ScanConfig)
    relay: RelayConfig = field(default_factory=RelayConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    routing: List[RouteConfig] = field(default_factory=list)
    path_mappings: List[PathMapping] = field(default_factory=list)
    
    # Runtime options
    dryrun: bool = True
    log_level: str = "INFO"
    
    def __post_init__(self):
        # Apply environment variable overrides
        self.dryrun = os.environ.get("DRYRUN", "true").lower() == "true"
        self.log_level = os.environ.get("REFRESHER_LOG_LEVEL", self.log_level)
        
        # Sort routing by prefix length (longest first) for proper matching
        self.routing.sort(key=lambda r: len(r.prefix), reverse=True)


def load_yaml_config(config_path: str) -> dict:
    """
    Load configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file
        
    Returns:
        Dictionary containing the parsed YAML configuration, or empty dict on error
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML config at {config_path}: {e}")
        return {}
    except Exception as e:
        print(f"Error loading config from {config_path}: {e}")
        return {}


def parse_scan_config(data: dict) -> ScanConfig:
    """Parse scan configuration from YAML data."""
    scan_data = data.get("scan", {})
    
    roots = scan_data.get("roots", [])
    mount_checks = scan_data.get("mount_checks", [])
    
    # Parse rewrites
    rewrites = []
    for r in scan_data.get("rewrites", []):
        from_path = r.get("from", "")
        to_path = r.get("to", "")
        if from_path and to_path:
            rewrites.append((from_path, to_path))
    
    # Get interval from YAML or environment
    interval = scan_data.get("interval")
    if interval is None:
        try:
            interval = int(os.environ.get("SCAN_INTERVAL", "300"))
        except (ValueError, TypeError):
            interval = 300
    
    # Parse ignore patterns
    ignore_patterns = scan_data.get("ignore_patterns", [])
    ignore_substr = os.environ.get("IGNORE_SUBSTR", "")
    if ignore_substr:
        ignore_patterns.append(ignore_substr)
    
    return ScanConfig(
        roots=roots,
        mount_checks=mount_checks,
        rewrites=rewrites,
        interval=interval,
        ignore_patterns=ignore_patterns
    )


def parse_routing(data: dict) -> List[RouteConfig]:
    """Parse routing configuration from YAML data."""
    routing_data = data.get("routing", [])
    routes = []
    
    for r in routing_data:
        prefix = r.get("prefix", "").rstrip("/")
        route_type = r.get("type", "")
        if prefix and route_type:
            routes.append(RouteConfig(prefix=prefix, type=route_type))
    
    return routes


def parse_path_mappings(data: dict) -> List[PathMapping]:
    """Parse path mappings from YAML data."""
    mappings_data = data.get("path_mappings", [])
    mappings = []
    
    for m in mappings_data:
        container = m.get("container", "")
        logical = m.get("logical", "")
        description = m.get("description", "")
        if container and logical:
            mappings.append(PathMapping(
                container_path=container,
                logical_path=logical,
                description=description
            ))
    
    return mappings


def parse_relay_config(data: dict) -> RelayConfig:
    """Parse relay configuration from YAML data."""
    relay_data = data.get("relay", {})
    
    return RelayConfig(
        base_url=relay_data.get("base_url", ""),
        token=relay_data.get("token", ""),
        base_env=relay_data.get("base_env", "RELAY_BASE"),
        token_env=relay_data.get("token_env", "RELAY_TOKEN")
    )


def parse_database_config(data: dict) -> DatabaseConfig:
    """Parse database configuration from YAML data."""
    db_data = data.get("database", {})
    
    return DatabaseConfig(
        path=db_data.get("path", ""),
        data_dir=db_data.get("data_dir", "/data")
    )


def parse_notification_config(data: dict) -> NotificationConfig:
    """Parse notification configuration from YAML data."""
    notif_data = data.get("notifications", {})
    
    return NotificationConfig(
        discord_webhook=notif_data.get("discord_webhook", ""),
        enabled=notif_data.get("enabled", True)
    )


def load_config(config_path: Optional[str] = None) -> RefresherrConfig:
    """
    Load the complete Refresherr configuration.
    
    Configuration is loaded from:
    1. YAML file (if provided or found at CONFIG_FILE env var)
    2. Environment variables (override YAML)
    3. Defaults
    
    Args:
        config_path: Optional path to YAML config file. If None, uses CONFIG_FILE env var
                     or defaults to /config/config.yaml
        
    Returns:
        RefresherrConfig object with complete configuration
    """
    if config_path is None:
        config_path = os.environ.get("CONFIG_FILE", "/config/config.yaml")
    
    # Load YAML data
    yaml_data = load_yaml_config(config_path)
    
    # Parse each section
    scan_config = parse_scan_config(yaml_data)
    relay_config = parse_relay_config(yaml_data)
    db_config = parse_database_config(yaml_data)
    notif_config = parse_notification_config(yaml_data)
    routing = parse_routing(yaml_data)
    path_mappings = parse_path_mappings(yaml_data)
    
    # Create main config
    config = RefresherrConfig(
        scan=scan_config,
        relay=relay_config,
        database=db_config,
        notifications=notif_config,
        routing=routing,
        path_mappings=path_mappings
    )
    
    return config


# Path translation helpers

def container_to_logical(path: str, mappings: List[PathMapping]) -> str:
    """
    Translate a container path to a logical (host) path.
    
    Args:
        path: Path inside the container
        mappings: List of PathMapping objects
        
    Returns:
        Translated logical path, or original path if no mapping found
    """
    for mapping in mappings:
        if path.startswith(mapping.container_path):
            # Replace the container prefix with logical prefix
            relative = path[len(mapping.container_path):].lstrip("/")
            logical = os.path.join(mapping.logical_path, relative)
            return logical
    return path


def logical_to_container(path: str, mappings: List[PathMapping]) -> str:
    """
    Translate a logical (host) path to a container path.
    
    Args:
        path: Logical/host path
        mappings: List of PathMapping objects
        
    Returns:
        Translated container path, or original path if no mapping found
    """
    for mapping in mappings:
        if path.startswith(mapping.logical_path):
            # Replace the logical prefix with container prefix
            relative = path[len(mapping.logical_path):].lstrip("/")
            container = os.path.join(mapping.container_path, relative)
            return container
    return path


def route_for_path(path: str, routing: List[RouteConfig]) -> Optional[str]:
    """
    Determine the route type for a given path.
    
    Args:
        path: File path to route
        routing: List of RouteConfig objects (should be sorted by prefix length)
        
    Returns:
        Route type (e.g., "sonarr_tv", "radarr_4k") or None if no match
    """
    for route in routing:
        if path.startswith(route.prefix):
            return route.type
    return None


def apply_rewrites(target: str, rewrites: List[Tuple[str, str]]) -> str:
    """
    Apply path rewrites to a target path.
    
    Args:
        target: Original target path
        rewrites: List of (from, to) tuples for path rewriting
        
    Returns:
        Rewritten path
    """
    for src, dst in rewrites:
        if src and target.startswith(src):
            return target.replace(src, dst, 1)
    return target


# Singleton pattern for global config access
_global_config: Optional[RefresherrConfig] = None


def get_config(config_path: Optional[str] = None, reload: bool = False) -> RefresherrConfig:
    """
    Get the global configuration instance.
    
    Args:
        config_path: Optional path to config file (only used on first load or reload)
        reload: If True, force reload the configuration
        
    Returns:
        RefresherrConfig instance
    """
    global _global_config
    
    if _global_config is None or reload:
        _global_config = load_config(config_path)
    
    return _global_config


def to_dict(config: RefresherrConfig) -> dict:
    """
    Convert RefresherrConfig to a dictionary for serialization (e.g., JSON API).
    
    Args:
        config: RefresherrConfig instance
        
    Returns:
        Dictionary representation of the configuration
    """
    return {
        "scan": {
            "roots": config.scan.roots,
            "mount_checks": config.scan.mount_checks,
            "rewrites": [{"from": r[0], "to": r[1]} for r in config.scan.rewrites],
            "interval": config.scan.interval,
            "ignore_patterns": config.scan.ignore_patterns
        },
        "relay": {
            "base_url": config.relay.base_url,
            "token_set": bool(config.relay.token),  # Don't expose the actual token
            "base_env": config.relay.base_env,
            "token_env": config.relay.token_env
        },
        "database": {
            "path": config.database.path,
            "data_dir": config.database.data_dir
        },
        "notifications": {
            "discord_webhook_set": bool(config.notifications.discord_webhook),
            "enabled": config.notifications.enabled
        },
        "routing": [
            {"prefix": r.prefix, "type": r.type}
            for r in config.routing
        ],
        "path_mappings": [
            {
                "container_path": m.container_path,
                "logical_path": m.logical_path,
                "description": m.description
            }
            for m in config.path_mappings
        ],
        "dryrun": config.dryrun,
        "log_level": config.log_level
    }
