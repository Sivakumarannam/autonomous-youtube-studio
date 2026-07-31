"""Unit tests for health endpoints."""
import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    async def test_health_returns_service_name(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        assert "service" in data
        assert "Autonomous" in data["service"]

    async def test_health_returns_timestamp(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        assert "timestamp" in data

    async def test_health_returns_env(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        assert "env" in data

    async def test_health_detailed(self, client: AsyncClient):
        response = await client.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "checks" in data
        assert "status" in data

    async def test_health_detailed_database_check(self, client: AsyncClient):
        response = await client.get("/health/detailed")
        data = response.json()
        # Database may be ok or error in test env (sqlite), just confirm key exists
        assert "database" in data["checks"]

    async def test_health_detailed_llm_provider(self, client: AsyncClient):
        response = await client.get("/health/detailed")
        data = response.json()
        assert "llm_provider" in data["checks"]