import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock
from data_fetcher import DataFetcher

@pytest.fixture
def fetcher():
    return DataFetcher(api_token="TEST_TOKEN")

@pytest.mark.asyncio
async def test_connect_failure(fetcher):
    # ws_url is set in __init__
    with patch("websockets.connect", side_effect=Exception("Connection refused")):
        success = await fetcher.connect()
        assert success is False
        assert fetcher.ws is None

@pytest.mark.asyncio
async def test_fetch_tick_success(fetcher):
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    tick_data = json.dumps({
        "tick": {
            "quote": 1234.56,
            "epoch": 1600000000,
            "symbol": "R_25"
        }
    })
    mock_ws.recv = AsyncMock(return_value=tick_data)
    mock_ws.closed = False
    fetcher.ws = mock_ws
    fetcher.is_connected = True
    
    tick = await fetcher.fetch_tick("R_25")
    assert tick == 1234.56

@pytest.mark.asyncio
async def test_fetch_timeframe_timeout(fetcher):
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_ws.closed = False
    fetcher.ws = mock_ws
    fetcher.is_connected = True

    with patch("data_fetcher.logger"):
        result = await fetcher.fetch_timeframe("R_25", "1m", count=10)
        assert result is None

@pytest.mark.asyncio
async def test_get_balance_success(fetcher):
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    balance_data = json.dumps({
        "balance": {
            "balance": 10000.0,
            "currency": "USD"
        }
    })
    mock_ws.recv = AsyncMock(return_value=balance_data)
    mock_ws.closed = False
    fetcher.ws = mock_ws
    fetcher.is_connected = True
    
    balance = await fetcher.get_balance()
    assert balance == 10000.0

@pytest.mark.asyncio
async def test_disconnect(fetcher):
    mock_ws = AsyncMock()
    mock_ws.close = AsyncMock()
    fetcher.ws = mock_ws
    fetcher.is_connected = True
    
    await fetcher.disconnect()
    assert fetcher.ws is None
    assert fetcher.is_connected is False
    mock_ws.close.assert_called()

@pytest.mark.asyncio
async def test_authorize_failure(fetcher):
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    error_resp = json.dumps({"error": {"message": "Invalid token"}})
    mock_ws.recv = AsyncMock(return_value=error_resp)
    mock_ws.closed = False
    fetcher.ws = mock_ws
    fetcher.is_connected = True
    
    success = await fetcher.authorize()
    assert success is False
    assert fetcher.last_error == "Auth failed: Invalid token"
