import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.websockets import WebSocketDisconnect

import create_admin as create_admin_mod
import verify_fixes
from app.bot.telegram_bridge import TelegramBridge
from app.core import auth as auth_mod
from app.ws import live as live_mod


class _QueryChain:
    def __init__(self, response):
        self._response = response

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def single(self):
        return self

    def update(self, *_args, **_kwargs):
        return self

    def execute(self):
        return self._response


@pytest.mark.asyncio
async def test_create_admin_paths(monkeypatch, capsys):
    # user not found path
    supabase = MagicMock()
    supabase.table.return_value = _QueryChain(SimpleNamespace(data=[]))
    monkeypatch.setattr(create_admin_mod, "supabase", supabase)
    await create_admin_mod.create_admin("missing@example.com")
    assert "No user found" in capsys.readouterr().out

    # already admin path
    data = [{"id": "u1", "role": "admin", "is_approved": True}]
    supabase.table.return_value = _QueryChain(SimpleNamespace(data=data))
    await create_admin_mod.create_admin("admin@example.com")
    assert "already an admin" in capsys.readouterr().out

    # cancel path
    data = [{"id": "u2", "role": "user", "is_approved": False}]
    table_calls = [
        _QueryChain(SimpleNamespace(data=data)),
        _QueryChain(SimpleNamespace(data=[])),
    ]
    supabase.table.side_effect = lambda *_a, **_k: table_calls.pop(0)
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    await create_admin_mod.create_admin("cancel@example.com")
    assert "Operation cancelled" in capsys.readouterr().out

    # successful update path
    data = [{"id": "u3", "role": "user", "is_approved": False}]
    table_calls = [
        _QueryChain(SimpleNamespace(data=data)),
        _QueryChain(SimpleNamespace(data=[{"id": "u3"}])),
    ]
    supabase.table.side_effect = lambda *_a, **_k: table_calls.pop(0)
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    await create_admin_mod.create_admin("ok@example.com")
    assert "Successfully promoted" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_create_admin_exception_path(monkeypatch, capsys):
    supabase = MagicMock()
    supabase.table.side_effect = RuntimeError("boom")
    monkeypatch.setattr(create_admin_mod, "supabase", supabase)
    await create_admin_mod.create_admin("err@example.com")
    assert "An error occurred" in capsys.readouterr().out


def test_verify_fixes_and_summary_paths(monkeypatch, capsys):
    try:
        checks = verify_fixes.verify_imports()
        assert checks and all(isinstance(c[1], bool) for c in checks)

        ok_code = verify_fixes.summary([("a", True), ("b", True)])
        bad_code = verify_fixes.summary([("a", True), ("b", False)])
        assert ok_code == 0
        assert bad_code == 1

        # early-fail branch in verify_imports()
        real_import = __import__

        def fail_import(name, *args, **kwargs):
            if name == "risefallbot":
                raise ImportError("forced import failure")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fail_import)
        checks = verify_fixes.verify_imports()
        assert checks and checks[-1][1] is False
        assert "FAIL" in capsys.readouterr().out
    finally:
        # verify_fixes disables logging globally at import time
        logging.disable(logging.NOTSET)


@pytest.mark.asyncio
async def test_auth_core_branches(monkeypatch):
    # no credentials
    assert await auth_mod.get_current_user(None) is None

    user = SimpleNamespace(id="u1", email="admin@example.com", created_at="2024-01-01")

    class _Auth:
        def get_user(self, _token):
            return SimpleNamespace(user=user)

    class _Supabase:
        def __init__(self, profile_data):
            self.auth = _Auth()
            self._profile_data = profile_data
            self.updated = False

        def table(self, _name):
            outer = self

            class _T:
                def select(self, *_a, **_k):
                    return self

                def update(self, *_a, **_k):
                    outer.updated = True
                    return self

                def eq(self, *_a, **_k):
                    return self

                def single(self):
                    return self

                def execute(self):
                    return SimpleNamespace(data=outer._profile_data)

            return _T()

    monkeypatch.setattr(auth_mod.settings, "INITIAL_ADMIN_EMAIL", "admin@example.com")

    supabase = _Supabase({"role": "user", "is_approved": False, "created_at": "x"})
    monkeypatch.setattr(auth_mod, "supabase", supabase)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    out = await auth_mod.get_current_user(creds)
    assert out["role"] == "admin"
    assert out["is_approved"] is True
    assert supabase.updated is True

    # missing profile branch + auto admin fallback
    supabase = _Supabase(None)
    monkeypatch.setattr(auth_mod, "supabase", supabase)
    out = await auth_mod.get_current_user(creds)
    assert out["role"] == "admin"
    assert out["is_approved"] is True

    # get_user exception branch
    class _BadAuth:
        def get_user(self, _token):
            raise RuntimeError("auth failed")

    bad_supabase = SimpleNamespace(auth=_BadAuth())
    monkeypatch.setattr(auth_mod, "supabase", bad_supabase)
    assert await auth_mod.get_current_user(creds) is None

    with pytest.raises(HTTPException) as exc:
        await auth_mod.require_login(None)
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        await auth_mod.require_auth({"is_approved": False})
    assert exc.value.status_code == 403

    assert await auth_mod.optional_auth({"id": "u"}) == {"id": "u"}


@pytest.mark.asyncio
async def test_ws_live_and_token_decode_branches(monkeypatch):
    monkeypatch.setattr(live_mod.jwt, "decode", lambda *_a, **_k: {"sub": "user-1"})
    assert live_mod.extract_user_id_from_token("tok") == "user-1"

    def _bad_decode(*_a, **_k):
        raise ValueError("bad token")

    monkeypatch.setattr(live_mod.jwt, "decode", _bad_decode)
    assert live_mod.extract_user_id_from_token("tok") is None

    # authenticated websocket path
    ws = AsyncMock()
    ws.headers = {}
    ws.receive_text.side_effect = ["hello", asyncio.TimeoutError(), WebSocketDisconnect()]

    bot = MagicMock()
    bot.state.get_status.return_value = {"status": "running"}
    bot.state.get_statistics.return_value = {"total": 1}

    event_mgr = SimpleNamespace(connect=AsyncMock(), disconnect=MagicMock())
    monkeypatch.setattr(live_mod, "event_manager", event_mgr)
    monkeypatch.setattr(live_mod.bot_manager, "get_bot", lambda _uid: bot)
    monkeypatch.setattr(live_mod.settings, "WS_REQUIRE_AUTH", False)
    monkeypatch.setattr(live_mod, "extract_user_id_from_token", lambda _t: "user-1")

    await live_mod.websocket_live(ws, token="token")
    assert ws.send_json.await_count >= 3
    event_mgr.connect.assert_awaited()
    event_mgr.disconnect.assert_called()

    # auth-required reject path
    ws2 = AsyncMock()
    ws2.headers = {}
    ws2.close = AsyncMock()
    monkeypatch.setattr(live_mod.settings, "WS_REQUIRE_AUTH", True)
    monkeypatch.setattr(live_mod, "extract_user_id_from_token", lambda _t: None)
    await live_mod.websocket_live(ws2, token="bad")
    ws2.close.assert_awaited()


@pytest.mark.asyncio
async def test_telegram_bridge_paths(monkeypatch):
    notifier = SimpleNamespace(
        enabled=True,
        notify_bot_started=AsyncMock(),
        notify_bot_stopped=AsyncMock(),
        notify_signal=AsyncMock(),
        notify_trade_opened=AsyncMock(),
        notify_trade_closed=AsyncMock(),
        notify_error=AsyncMock(),
        notify_connection_lost=AsyncMock(),
        notify_connection_restored=AsyncMock(),
        notify_daily_summary=AsyncMock(),
    )

    monkeypatch.setattr("app.bot.telegram_bridge.notifier", notifier)
    monkeypatch.setattr("app.bot.telegram_bridge.TELEGRAM_AVAILABLE", True)
    bridge = TelegramBridge()
    assert bridge.active is True

    await bridge.notify_bot_started(100.0, 1.0, "Conservative")
    await bridge.notify_bot_stopped({"wins": 1})
    await bridge.notify_signal({"signal": "BUY"})
    await bridge.notify_signal({"signal": "HOLD"})
    await bridge.notify_trade_opened({"symbol": "R_50"})
    await bridge.notify_trade_closed({"contract_id": "1", "exit_price": 1.2}, 2.5, "won")
    await bridge.notify_error("oops")
    await bridge.notify_connection_lost()
    await bridge.notify_connection_restored()
    await bridge.send_daily_summary({"trades": 3})

    assert notifier.notify_bot_started.await_count == 1
    assert notifier.notify_signal.await_count == 1

    # inactive bridge no-op
    monkeypatch.setattr("app.bot.telegram_bridge.TELEGRAM_AVAILABLE", False)
    bridge2 = TelegramBridge()
    assert bridge2.active is False
    await bridge2.notify_error("ignored")
