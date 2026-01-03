"""
Data Fetcher for Deriv R_25 Trading Bot
Asynchronous data fetching from Deriv API with auto-reconnect
data_fetcher.py - WITH AUTO-RECONNECT AND MULTI-TIMEFRAME SUPPORT
"""

import asyncio
import websockets
import json
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime
import config
from utils import setup_logger, parse_candle_data

# Setup logger
logger = setup_logger()

class DataFetcher:
    """Handles all data fetching operations from Deriv API"""
    
    def __init__(self, api_token: str, app_id: str = "1089"):
        """
        Initialize DataFetcher
        
        Args:
            api_token: Deriv API token
            app_id: Deriv app ID
        """
        self.api_token = api_token
        self.app_id = app_id
        self.ws_url = f"{config.WS_URL}?app_id={app_id}"
        self.ws = None
        self.is_connected = False
        self.request_lock = asyncio.Lock()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
    
    async def connect(self) -> bool:
        """
        Connect to Deriv WebSocket API
        
        Returns:
            True if connected successfully
        """
        try:
            self.ws = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10
            )
            self.is_connected = True
            self.reconnect_attempts = 0  # Reset on successful connection
            logger.info("[OK] Connected to Deriv API")
            
            # Authorize
            await self.authorize()
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to Deriv API: {e}")
            self.is_connected = False
            return False
    
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to the API
        
        Returns:
            True if reconnected successfully
        """
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts > self.max_reconnect_attempts:
            logger.error(f"[ERROR] Max reconnection attempts ({self.max_reconnect_attempts}) reached")
            return False
        
        logger.warning(f"[RECONNECT] Attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")
        
        # Close existing connection if any
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        
        self.is_connected = False
        
        # Wait before reconnecting (exponential backoff)
        wait_time = min(2 ** self.reconnect_attempts, 30)
        logger.info(f"[RECONNECT] Waiting {wait_time}s before reconnecting...")
        await asyncio.sleep(wait_time)
        
        # Try to connect
        return await self.connect()
    
    async def ensure_connected(self) -> bool:
        """
        Ensure WebSocket is connected, reconnect if needed
        
        Returns:
            True if connected
        """
        if not self.is_connected or not self.ws or self.ws.closed:
            logger.warning("[WARNING] Connection lost, attempting to reconnect...")
            return await self.reconnect()
        return True
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        if self.ws:
            await self.ws.close()
            self.is_connected = False
            logger.info("[DISCONNECTED] From Deriv API")
    
    async def authorize(self) -> bool:
        """
        Authorize connection with API token
        
        Returns:
            True if authorized successfully
        """
        try:
            auth_request = {
                "authorize": self.api_token
            }
            
            async with self.request_lock:
                await self.ws.send(json.dumps(auth_request))
                response = await self.ws.recv()
                data = json.loads(response)
            
            if "error" in data:
                logger.error(f"[ERROR] Authorization failed: {data['error']['message']}")
                return False
            
            if "authorize" in data:
                logger.info("[OK] Authorization successful")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[ERROR] Authorization error: {e}")
            return False
    
    async def send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send request to API and get response (with reconnection handling)
        
        Args:
            request: Request dictionary
        
        Returns:
            Response dictionary
        """
        try:
            # Ensure connection is alive
            if not await self.ensure_connected():
                return {"error": {"message": "Failed to establish connection"}}
            
            async with self.request_lock:
                await self.ws.send(json.dumps(request))
                response = await self.ws.recv()
                return json.loads(response)
                
        except (websockets.exceptions.ConnectionClosed, 
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK) as e:
            logger.warning(f"[WARNING] Connection closed during request: {e}")
            
            # Try to reconnect and retry the request once
            if await self.reconnect():
                try:
                    async with self.request_lock:
                        await self.ws.send(json.dumps(request))
                        response = await self.ws.recv()
                        return json.loads(response)
                except Exception as retry_error:
                    logger.error(f"[ERROR] Retry failed: {retry_error}")
                    return {"error": {"message": str(retry_error)}}
            
            return {"error": {"message": "Connection lost and reconnection failed"}}
            
        except Exception as e:
            logger.error(f"[ERROR] Request error: {e}")
            return {"error": {"message": str(e)}}
    
    async def fetch_candles(self, symbol: str, granularity: int, 
                           count: int) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data
        
        Args:
            symbol: Trading symbol (e.g., 'R_25')
            granularity: Candle granularity in seconds (60, 300, etc.)
            count: Number of candles to fetch
        
        Returns:
            DataFrame with OHLC data or None if failed
        """
        try:
            request = {
                "ticks_history": symbol,
                "adjust_start_time": 1,
                "count": count,
                "end": "latest",
                "start": 1,
                "style": "candles",
                "granularity": granularity
            }
            
            response = await self.send_request(request)
            
            if "error" in response:
                logger.error(f"[ERROR] Failed to fetch candles: {response['error']['message']}")
                return None
            
            if "candles" not in response:
                logger.error("[ERROR] No candle data in response")
                return None
            
            # Parse candles
            candles = response["candles"]
            
            df = pd.DataFrame({
                'timestamp': [c['epoch'] for c in candles],
                'open': [float(c['open']) for c in candles],
                'high': [float(c['high']) for c in candles],
                'low': [float(c['low']) for c in candles],
                'close': [float(c['close']) for c in candles]
            })
            
            # Convert timestamp to datetime
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            
            logger.info(f"[OK] Fetched {len(df)} candles ({granularity}s)")
            return df
            
        except Exception as e:
            logger.error(f"[ERROR] Error fetching candles: {e}")
            return None
    
    async def fetch_tick(self, symbol: str) -> Optional[float]:
        """
        Fetch current tick (price)
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Current price or None if failed
        """
        try:
            request = {
                "ticks": symbol
            }
            
            response = await self.send_request(request)
            
            if "error" in response:
                logger.error(f"[ERROR] Failed to fetch tick: {response['error']['message']}")
                return None
            
            if "tick" in response:
                return float(response["tick"]["quote"])
            
            return None
            
        except Exception as e:
            logger.error(f"[ERROR] Error fetching tick: {e}")
            return None
    
    async def get_balance(self) -> Optional[float]:
        """
        Get account balance
        
        Returns:
            Account balance or None if failed
        """
        try:
            request = {"balance": 1, "subscribe": 0}
            response = await self.send_request(request)
            
            if "error" in response:
                logger.error(f"[ERROR] Failed to get balance: {response['error']['message']}")
                return None
            
            if "balance" in response:
                return float(response["balance"]["balance"])
            
            return None
            
        except Exception as e:
            logger.error(f"[ERROR] Error getting balance: {e}")
            return None
    
    async def get_active_symbols(self) -> Optional[List[Dict]]:
        """
        Get list of active trading symbols
        
        Returns:
            List of symbol dictionaries or None if failed
        """
        try:
            request = {
                "active_symbols": "brief",
                "product_type": "basic"
            }
            
            response = await self.send_request(request)
            
            if "error" in response:
                logger.error(f"[ERROR] Failed to get symbols: {response['error']['message']}")
                return None
            
            if "active_symbols" in response:
                return response["active_symbols"]
            
            return None
            
        except Exception as e:
            logger.error(f"[ERROR] Error getting symbols: {e}")
            return None
    
    async def fetch_multi_timeframe_data(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple timeframes SEQUENTIALLY (not concurrently)
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Dictionary with timeframe data {granularity: DataFrame}
        """
        try:
            result = {}
            
            # Fetch 1m candles first
            candles_1m = await self.fetch_candles(symbol, 60, config.CANDLES_1M)
            if candles_1m is not None:
                result['1m'] = candles_1m
            
            # Then fetch 5m candles
            candles_5m = await self.fetch_candles(symbol, 300, config.CANDLES_5M)
            if candles_5m is not None:
                result['5m'] = candles_5m
            
            return result
            
        except Exception as e:
            logger.error(f"[ERROR] Error fetching multi-timeframe data: {e}")
            return {}
    
    # ============================================================================
    # NEW METHODS FOR MULTI-TIMEFRAME SUPPORT (Top-Down Strategy)
    # ============================================================================
    
    async def fetch_timeframe(self, symbol: str, timeframe: str, count: int = 200) -> Optional[pd.DataFrame]:
        """
        Fetch data for any timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)
        
        Args:
            symbol: Trading symbol (e.g., 'R_25')
            timeframe: Timeframe string ('1m', '5m', '15m', '1h', '4h', '1d', '1w')
            count: Number of candles to fetch
        
        Returns:
            DataFrame with OHLC data or None if failed
        """
        # Convert timeframe to Deriv granularity (seconds)
        granularity_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400,
            '1w': 604800
        }
        
        if timeframe not in granularity_map:
            logger.error(f"[ERROR] Unsupported timeframe: {timeframe}")
            return None
        
        granularity = granularity_map[timeframe]
        
        try:
            logger.debug(f"Fetching {count} {timeframe} candles...")
            df = await self.fetch_candles(symbol, granularity, count)
            
            if df is not None:
                logger.info(f"[OK] Fetched {len(df)} {timeframe} candles")
            else:
                logger.warning(f"[WARNING] Failed to fetch {timeframe} candles")
            
            return df
            
        except Exception as e:
            logger.error(f"[ERROR] Error fetching {timeframe} data: {e}")
            return None
    
    async def fetch_all_timeframes(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """
        Fetch all timeframes needed for Top-Down strategy
        Fetches SEQUENTIALLY with rate limiting (not concurrent)
        
        Args:
            symbol: Trading symbol (e.g., 'R_25')
        
        Returns:
            Dictionary with keys: '1m', '5m', '1h', '4h', '1d', '1w'
        """
        timeframes = {
            '1m': 100,   # 100 1-minute candles
            '5m': 100,   # 100 5-minute candles  
            '1h': 200,   # 200 hours (~8 days)
            '4h': 200,   # 200 4-hour candles (~33 days)
            '1d': 100,   # 100 days (~3 months)
            '1w': 52     # 52 weeks (1 year)
        }
        
        data = {}
        
        logger.info(f"[INFO] Fetching all timeframes for {symbol}...")
        
        for tf, count in timeframes.items():
            try:
                df = await self.fetch_timeframe(symbol, tf, count)
                if df is not None and not df.empty:
                    data[tf] = df
                else:
                    logger.warning(f"[WARNING] Empty or failed {tf} data")
                
                # Rate limiting: Wait between requests
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"[ERROR] Failed to fetch {tf}: {e}")
        
        logger.info(f"[OK] Fetched {len(data)}/{len(timeframes)} timeframes successfully")
        
        return data


async def get_market_data(symbol: str = "R_25") -> Dict[str, pd.DataFrame]:
    """
    Main function to fetch market data
    
    Args:
        symbol: Trading symbol
    
    Returns:
        Dictionary with market data for different timeframes
    """
    fetcher = DataFetcher(config.DERIV_API_TOKEN, config.DERIV_APP_ID)
    
    try:
        # Connect
        connected = await fetcher.connect()
        if not connected:
            return {}
        
        # Fetch data
        data = await fetcher.fetch_multi_timeframe_data(symbol)
        
        return data
        
    finally:
        # Always disconnect
        await fetcher.disconnect()


async def get_all_timeframes_data(symbol: str = "R_25") -> Dict[str, pd.DataFrame]:
    """
    Main function to fetch ALL timeframes for top-down analysis
    
    Args:
        symbol: Trading symbol
    
    Returns:
        Dictionary with market data for all timeframes (1m, 5m, 1h, 4h, 1d, 1w)
    """
    fetcher = DataFetcher(config.DERIV_API_TOKEN, config.DERIV_APP_ID)
    
    try:
        # Connect
        connected = await fetcher.connect()
        if not connected:
            return {}
        
        # Fetch all timeframes
        data = await fetcher.fetch_all_timeframes(symbol)
        
        return data
        
    finally:
        # Always disconnect
        await fetcher.disconnect()