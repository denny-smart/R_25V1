"""
Unit tests for app.core.cache.RedisCache
Covers initialization, basic operations, error handling, pattern deletes, and singleton behavior.

Framework: pytest
"""
from typing import Any, Dict, List
import json
import fnmatch
import pytest


# NOTE: Import the module under test and the Settings singleton it uses
import app.core.cache as cache_mod
from app.core.cache import RedisCache, settings


class FakeRedis:
    """A simple in-memory fake for redis.Redis with minimal API used by RedisCache."""
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: str | None = None,
                 decode_responses: bool = True, socket_connect_timeout: int = 2, socket_timeout: int = 2):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.decode_responses = decode_responses
        self.socket_connect_timeout = socket_connect_timeout
        self.socket_timeout = socket_timeout
        self._store: Dict[str, str] = {}
        self._pinged = False

    # Connection methods
    def ping(self) -> bool:
        self._pinged = True
        return True

    # KV methods
    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        # Ignore ttl in fake; store raw value
        self._store[key] = value
        return True

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count

    def keys(self, pattern: str) -> List[str]:
        return [k for k in list(self._store.keys()) if fnmatch.fnmatch(k, pattern)]


class FailingPingRedis(FakeRedis):
    def ping(self) -> bool:
        raise RuntimeError("cannot ping")


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    """Ensure a fresh RedisCache singleton per test and neutral default settings."""
    # Reset the class-level singleton and module-level global instance safety
    RedisCache._instance = None  # type: ignore[attr-defined]
    # Default: disable redis unless test enables it
    monkeypatch.setattr(settings, "REDIS_HOST", None, raising=False)
    monkeypatch.setattr(settings, "REDIS_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "REDIS_PORT", 6379, raising=False)
    monkeypatch.setattr(settings, "REDIS_DB", 0, raising=False)
    monkeypatch.setattr(settings, "REDIS_PASSWORD", None, raising=False)
    yield
    # Cleanup after test
    RedisCache._instance = None  # type: ignore[attr-defined]


def _init_enabled_cache(monkeypatch, redis_impl=FakeRedis) -> RedisCache:
    """Helper to enable redis in settings and return an initialized RedisCache with a fake client."""
    monkeypatch.setattr(settings, "REDIS_HOST", "localhost", raising=False)
    monkeypatch.setattr(settings, "REDIS_ENABLED", True, raising=False)
    # Patch the redis.Redis class used inside the module
    monkeypatch.setattr(cache_mod.redis, "Redis", redis_impl)
    inst = RedisCache()
    assert inst.enabled is True, "RedisCache should be enabled when REDIS is configured and ping succeeds"
    assert isinstance(inst.client, redis_impl)
    return inst


# ----------------------------------------------------------------------------
# Behaviors
# ----------------------------------------------------------------------------
# 1) Should be disabled and no-op when Redis is not configured
# 2) Should enable and perform basic get/set/delete operations with JSON encoding
# 3) Should handle connection failures (ping/init) gracefully and stay disabled
# 4) Should return None on JSON parse errors and False on serialization errors
# 5) Should delete keys by pattern using delete_pattern
# 6) Should treat delete as False when disabled and 0 for delete_pattern when disabled
# 7) Should guard re-initialization when already initialized (singleton __init__ guard)
# 8) Should return False from set when client raises exceptions
# ----------------------------------------------------------------------------


def test_disabled_when_not_configured(monkeypatch):
    # Ensure no redis config
    monkeypatch.setattr(settings, "REDIS_HOST", None, raising=False)
    monkeypatch.setattr(settings, "REDIS_ENABLED", False, raising=False)

    inst = RedisCache()
    assert inst.enabled is False
    assert inst.client is None

    # Operations should be safe no-ops
    assert inst.get("k") is None
    assert inst.set("k", {"x": 1}, ttl=10) is False
    assert inst.delete("k") is False
    assert inst.delete_pattern("a:*") == 0


def test_enable_and_basic_ops_work(monkeypatch):
    inst = _init_enabled_cache(monkeypatch, redis_impl=FakeRedis)

    # Set JSON-serializable value
    ok = inst.set("user:1", {"name": "Ada", "age": 37}, ttl=30)
    assert ok is True

    # Get returns parsed JSON
    got = inst.get("user:1")
    assert got == {"name": "Ada", "age": 37}

    # Delete returns True and removes key
    assert inst.delete("user:1") is True
    assert inst.get("user:1") is None


def test_connection_failure_graceful(monkeypatch):
    # Failing ping keeps cache disabled
    # Because FailingPingRedis.ping raises, __init__ should catch and disable
    RedisCache._instance = None  # fresh
    monkeypatch.setattr(settings, "REDIS_HOST", "localhost", raising=False)
    monkeypatch.setattr(settings, "REDIS_ENABLED", True, raising=False)
    monkeypatch.setattr(cache_mod.redis, "Redis", FailingPingRedis)

    inst = RedisCache()
    assert inst.enabled is False
    assert inst.client is None

    # Ops are safe no-ops
    assert inst.get("x") is None
    assert inst.set("x", 1) is False


def test_json_errors_handled(monkeypatch):
    inst = _init_enabled_cache(monkeypatch, redis_impl=FakeRedis)

    # Serialization error: non-serializable object
    class Unserializable:
        pass

    assert inst.set("bad", Unserializable()) is False

    # Insert invalid JSON directly via client; get() should swallow and return None
    assert isinstance(inst.client, FakeRedis)
    inst.client.setex("garbage", 10, "this-is-not-json")
    assert inst.get("garbage") is None


def test_delete_pattern_removes_matching_keys(monkeypatch):
    inst = _init_enabled_cache(monkeypatch, redis_impl=FakeRedis)

    # Populate keys
    assert inst.set("a:1", {"v": 1}) is True
    assert inst.set("a:2", {"v": 2}) is True
    assert inst.set("b:1", {"v": 3}) is True

    removed = inst.delete_pattern("a:*")
    assert removed == 2
    # Remaining key should still be present
    assert inst.get("b:1") == {"v": 3}


def test_delete_and_delete_pattern_when_disabled(monkeypatch):
    # Disabled instance
    inst = RedisCache()
    assert inst.enabled is False

    assert inst.delete("does_not_exist") is False
    assert inst.delete_pattern("*") == 0


def test_singleton_reinit_guard(monkeypatch):
    calls = {"ctor": 0}

    class CountingRedis(FakeRedis):
        def __init__(self, *a, **kw):
            calls["ctor"] += 1
            super().__init__(*a, **kw)

    # First creation initializes and pings once
    inst1 = _init_enabled_cache(monkeypatch, redis_impl=CountingRedis)
    assert calls["ctor"] == 1

    # Second creation should reuse singleton without re-calling ctor
    inst2 = RedisCache()
    assert inst2 is inst1
    assert calls["ctor"] == 1  # No new ctor call

    # Even if settings change, __init__ guard should prevent re-initialization
    monkeypatch.setattr(settings, "REDIS_HOST", None, raising=False)
    inst3 = RedisCache()
    assert inst3 is inst1
    assert calls["ctor"] == 1


def test_set_returns_false_on_client_exception(monkeypatch):
    class ErroringRedis(FakeRedis):
        def setex(self, key: str, ttl: int, value: str) -> bool:
            raise RuntimeError("boom")

    inst = _init_enabled_cache(monkeypatch, redis_impl=ErroringRedis)
    ok = inst.set("k", {"x": 1})
    assert ok is False
