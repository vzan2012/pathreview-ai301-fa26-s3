"""Tests for api/routes/health.py"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from api.routes.health import health_check
from core.config import settings


@pytest.mark.unit
class TestHealthCheckRedis:
    """Regression tests for issue #62: the Redis probe built its client from
    settings.redis_host/settings.redis_port, which don't exist on Settings
    (only redis_url does), so a real AttributeError always reported Redis as
    unhealthy, even when it was reachable."""

    @pytest.fixture
    def mock_db(self):
        """Mock async DB session whose Postgres check always succeeds, so
        these tests isolate the Redis check."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=None)
        return db

    @pytest.mark.asyncio
    async def test_redis_healthy_when_reachable(self, mock_db):
        """Reports redis healthy when the client can ping, built from
        settings.redis_url rather than the removed host/port fields."""
        mock_client = Mock()
        mock_client.ping = Mock(return_value=True)

        with patch("redis.Redis.from_url", return_value=mock_client) as mock_from_url:
            result = await health_check(db=mock_db)

        assert result["dependencies"]["redis"] == "healthy"
        mock_from_url.assert_called_once_with(settings.redis_url, decode_responses=True)

    @pytest.mark.asyncio
    async def test_redis_unhealthy_when_ping_fails(self, mock_db):
        """A genuine connection failure still reports redis unhealthy and a
        503 overall - the fix doesn't paper over a real outage."""
        with (
            patch("redis.Redis.from_url", side_effect=ConnectionError("refused")),
            pytest.raises(HTTPException) as exc_info,
        ):
            await health_check(db=mock_db)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["dependencies"]["redis"] == "unhealthy"
