import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import os

# Set environment variables for testing
os.environ["ENVIRONMENT"] = "development"
os.environ["JWT_SECRET_KEY"] = "test_secret"

from app.main import app

@pytest.fixture
def client():
    # Use TestClient for FastAPI
    # Setup any necessary mocks before creating the client
    with patch("app.bot.manager.bot_manager") as mock_bm:
        mock_bm.get_all_status.return_value = {"active_bots": 0}
        yield TestClient(app)

def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    # If 404, let's see what's wrong
    if response.status_code == 404:
        print(f"DEBUG: 404 for /health. Routes: {[r.path for r in app.routes]}")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_root_endpoint(client):
    """Test root information endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert "version" in response.json()
    assert response.json()["status"] == "operational"

def test_api_auth_status(client):
    """Test auth status endpoint structure"""
    response = client.get("/api/v1/auth/status")
    # This might return 401 if unauthorized, but should not be 404
    assert response.status_code in (200, 401)

def test_api_monitor_performance(client):
    """Test monitor performance endpoint"""
    response = client.get("/api/v1/monitor/performance")
    # Requires auth, so 401 is expected if not mocked. 404 is a failure.
    assert response.status_code in (200, 401)
