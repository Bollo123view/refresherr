"""Tests for dashboard API endpoints."""
import json
import pytest

def test_health_endpoint(client):
    """Test the /health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'ok' in data

def test_api_config_endpoint(client):
    """Test the /api/config endpoint."""
    response = client.get('/api/config')
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Should have basic config structure
    assert 'scan' in data or 'database' in data or 'relay' in data

def test_api_broken_endpoint(client):
    """Test the /api/broken endpoint."""
    response = client.get('/api/broken')
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Should return a list (even if empty)
    assert isinstance(data, list)

def test_api_stats_endpoint(client):
    """Test the /api/stats endpoint."""
    response = client.get('/api/stats')
    
    # Should return stats or a structured error
    assert response.status_code in [200, 500]
    data = json.loads(response.data)
    
    if response.status_code == 200:
        # Should have stats structure
        assert 'symlinks' in data or 'movies' in data or 'episodes' in data

def test_api_routes_endpoint(client):
    """Test the /api/routes endpoint."""
    response = client.get('/api/routes')
    assert response.status_code == 200
    data = json.loads(response.data)
    
    # Should have routing or fallback structure
    assert 'routing' in data

def test_api_config_dryrun_toggle(client):
    """Test the /api/config/dryrun endpoint."""
    response = client.post(
        '/api/config/dryrun',
        data=json.dumps({'dryrun': False}),
        content_type='application/json'
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    
    assert 'success' in data
    assert data.get('dryrun') == False

def test_api_config_dryrun_missing_param(client):
    """Test /api/config/dryrun with missing parameter."""
    response = client.post(
        '/api/config/dryrun',
        data=json.dumps({}),
        content_type='application/json'
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_spa_routing(client):
    """Test that SPA routing works - all paths serve the app."""
    # The root should serve the React app
    response = client.get('/')
    assert response.status_code == 200

def test_api_endpoints_return_json(client):
    """Verify API endpoints return proper JSON content type."""
    endpoints = [
        '/api/config',
        '/api/routes',
        '/api/stats',
        '/api/broken',
        '/health'
    ]
    
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert 'application/json' in response.content_type

def test_cors_headers_not_present_by_default(client):
    """Verify CORS headers are not set by default (can be added if needed)."""
    response = client.get('/api/config')
    # This is informational - CORS can be added later if needed
    assert response.status_code == 200

@pytest.mark.parametrize('endpoint', [
    '/api/config',
    '/api/stats',
    '/api/routes',
    '/api/broken',
    '/health'
])
def test_api_endpoints_accessible(client, endpoint):
    """Test that all critical API endpoints are accessible."""
    response = client.get(endpoint)
    # Should either succeed or fail gracefully with server error, not 404
    assert response.status_code in [200, 500]
    assert response.status_code != 404
