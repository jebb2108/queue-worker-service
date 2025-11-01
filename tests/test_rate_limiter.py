import asyncio
import pytest
import time
from src.infrastructure.services import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit():
    limiter = RateLimiter(max_requests=3, time_window=1)

    for i in range(3):
        assert await limiter.is_allowed(key="1") == True

    assert await limiter.is_allowed(key="1") == False


@pytest.mark.asyncio
async def test_rate_limiter_resets_after_window():
    limiter = RateLimiter(max_requests=2, time_window=1)

    assert await limiter.is_allowed(key="1") == True
    assert await limiter.is_allowed(key="1") == True
    assert await limiter.is_allowed(key="1") == False

    await asyncio.sleep(1.1)

    assert await limiter.is_allowed(key="1") == True
    assert await limiter.is_allowed(key="1") == True
    assert await limiter.is_allowed(key="1") == False


@pytest.mark.asyncio
async def test_rate_limiter_per_user():
    limiter = RateLimiter(max_requests=2, time_window=10)

    assert await limiter.is_allowed(key="1") == True
    assert await limiter.is_allowed(key="1") == True
    assert await limiter.is_allowed(key="1") == False

    assert await limiter.is_allowed(key="2") == True
    assert await limiter.is_allowed(key="2") == True
    assert await limiter.is_allowed(key="2") == False