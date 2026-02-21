import pytest
import pandas as pd
import json
from unittest.mock import MagicMock, AsyncMock, patch
from data_fetcher import DataFetcher

@pytest.fixture
def fetcher(mock_env_vars):
    with patch("data_fetcher.TokenBucket") as mock_bucket:
        mock_bucket_instance = MagicMock()
        mock_bucket_instance.acquire = AsyncMock()
        mock_bucket.return_value = mock_bucket_instance
        
        f = DataFetcher("fake_token", "1089")
        f.ws = MagicMock()
        f.ws.send = AsyncMock()
        f.ws.recv = AsyncMock()
        f.ws.closed = False  # CRITICAL: prevent ensure_connected from reconnecting
        f.is_connected = True
        return f

@pytest.mark.asyncio
async def test_data_fetcher_authorize(fetcher):
    """Test API authorization"""
    # Mock sequence of responses if needed, but for authorize one is enough
    fetcher.ws.recv.return_value = json.dumps({"msg_type": "authorize", "authorize": {"loginid": "CR123"}})
    res = await fetcher.authorize()
    assert res is True

@pytest.mark.asyncio
async def test_data_fetcher_fetch_candles_success(fetcher):
    """Test fetching candles successfully"""
    mock_candles = {
        "msg_type": "candles", 
        "candles": [
            {"epoch": 1700000000, "open": "100", "high": "105", "low": "95", "close": "102"},
            {"epoch": 1700000060, "open": "102", "high": "108", "low": "101", "close": "105"}
        ]
    }
    fetcher.ws.recv.return_value = json.dumps(mock_candles)
    
    # fetch_candles also calls authorize() internally or assumes it
    df = await fetcher.fetch_candles("R_25", "1m", count=2)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert df.iloc[0]['close'] == 102.0

@pytest.mark.asyncio
async def test_token_bucket():
    """Test TokenBucket logic directly"""
    from utils import TokenBucket
    # Use real TokenBucket but with fast time if possible or just test basic init
    limiter = TokenBucket(rate=100.0, capacity=10.0)
    await limiter.acquire(1.0)
    assert limiter.tokens <= 9.0 # Some tokens used
