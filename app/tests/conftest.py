"""Pytest configuration and fixtures for backend tests."""
import os
import sys
import tempfile
import pytest
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(app_dir))

# Add parent directory to path so 'app' package is importable
parent_dir = app_dir.parent
sys.path.insert(0, str(parent_dir))

@pytest.fixture
def app():
    """Create Flask app for testing."""
    # Import here to ensure proper path setup
    sys.path.insert(0, str(app_dir / "services" / "dashboard"))
    
    # Set test environment
    os.environ['DATA_DIR'] = tempfile.mkdtemp()
    os.environ['DRYRUN'] = 'true'
    os.environ['FLASK_ENV'] = 'testing'
    
    # Import app after setting environment
    from services.dashboard.app import app as flask_app
    
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    
    yield flask_app
    
    # Cleanup
    import shutil
    if os.path.exists(os.environ['DATA_DIR']):
        shutil.rmtree(os.environ['DATA_DIR'])

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create CLI runner."""
    return app.test_cli_runner()

@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_content = """
scan:
  roots:
    - /opt/media/jelly/tv
    - /opt/media/jelly/movies
  mount_checks:
    - /mnt/remote/realdebrid
  interval: 300

routing:
  - prefix: /opt/media/jelly/movies
    type: radarr_movie
  - prefix: /opt/media/jelly/tv
    type: sonarr_tv

path_mappings:
  - container: /opt/media/jelly
    logical: /mnt/storage/media/jelly
    description: "Jellyfin symlink root"
"""
        f.write(config_content)
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    if os.path.exists(config_path):
        os.unlink(config_path)
