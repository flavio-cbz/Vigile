import pytest
import asyncio
import time
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient
from master.core.rate_limiter import RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_is_allowed():
    limiter = RateLimiter(max_requests=2, window_seconds=1)
    
    # First 2 requests should be allowed
    assert await limiter.is_allowed("key1") is True
    assert await limiter.is_allowed("key1") is True
    
    # 3rd request should be blocked
    assert await limiter.is_allowed("key1") is False
    
    # Different key should still be allowed
    assert await limiter.is_allowed("key2") is True
    
    # Wait for window to expire
    await asyncio.sleep(1.05)
    
    # Now key1 should be allowed again
    assert await limiter.is_allowed("key1") is True

@pytest.mark.asyncio
async def test_rate_limiter_cleanup_expired():
    limiter = RateLimiter(max_requests=5, window_seconds=1)
    await limiter.is_allowed("key1")
    await limiter.is_allowed("key2")
    
    # Check that they exist in buckets
    assert "key1" in limiter._buckets
    assert "key2" in limiter._buckets
    
    # Wait for expiry
    await asyncio.sleep(1.05)
    
    await limiter.cleanup_expired()
    
    # Buckets should be cleared
    assert "key1" not in limiter._buckets
    assert "key2" not in limiter._buckets

def test_rate_limiter_middleware():
    limiter = RateLimiter(max_requests=2, window_seconds=10)
    app = FastAPI()
    limiter.middleware(app)

    @app.get("/test")
    def test_route():
        return {"status": "ok"}

    client = TestClient(app)

    # 1st request
    r1 = client.get("/test")
    assert r1.status_code == 200

    # 2nd request
    r2 = client.get("/test")
    assert r2.status_code == 200

    # 3rd request (blocked)
    r3 = client.get("/test")
    assert r3.status_code == 429
    assert r3.json() == {"error": "Too many requests", "retry_after": 10}

def test_rate_limiter_dependency():
    limiter = RateLimiter(max_requests=10, window_seconds=10)
    app = FastAPI()
    
    @app.get("/dep-test", dependencies=[Depends(limiter.dependency(max_requests=2))])
    def dep_route():
        return {"status": "ok"}

    client = TestClient(app)

    # 1st request
    r1 = client.get("/dep-test")
    assert r1.status_code == 200

    # 2nd request
    r2 = client.get("/dep-test")
    assert r2.status_code == 200

    # 3rd request (blocked by dependency)
    r3 = client.get("/dep-test")
    assert r3.status_code == 429
    assert "Too many requests" in r3.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limiter_uses_x_forwarded_for_only_from_trusted_proxy(monkeypatch):
    from master.config import settings

    limiter = RateLimiter(max_requests=1, window_seconds=10, trusted_proxies=["10.0.0.1"])
    app = FastAPI()
    limiter.middleware(app)
    monkeypatch.setattr(settings, "trusted_proxies", ["10.0.0.1"])

    @app.get("/xff-test")
    def xff_route(request: Request):
        return {"client": limiter.client_ip(request)}

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app, client=("10.0.0.1", 50000))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/xff-test", headers={"X-Forwarded-For": "203.0.113.10"})
        second = await client.get("/xff-test", headers={"X-Forwarded-For": "203.0.113.11"})

        assert first.status_code == 200
        assert first.json()["client"] == "203.0.113.10"
        assert second.status_code == 200

@pytest.mark.asyncio
async def test_rate_limiter_cleanup_task():
    limiter = RateLimiter()
    app = FastAPI()
    
    # 1. Normal run (runs once with small interval, then cancelled)
    task = limiter.start_cleanup_task(app, interval=0.01)
    await asyncio.sleep(0.03) # allow it to run
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert task.done()

    # 2. Error in loop (to hit exception handler)
    import unittest.mock as mock
    limiter_err = RateLimiter()
    with mock.patch.object(limiter_err, "cleanup_expired", side_effect=ValueError("cleanup failed")):
        task_err = limiter_err.start_cleanup_task(app, interval=0.01)
        await asyncio.sleep(0.03) # allow it to run and hit error
        task_err.cancel()
        try:
            await task_err
        except asyncio.CancelledError:
            pass
        assert task_err.done()
