"""
Rise/Fall R_25 Support & Resistance strategy.

6-gate entry model
------------------
1.  Load the last RF_SR_CANDLE_COUNT 1-minute OHLCV candles for R_25.
2.  Identify swing-high and swing-low pivot levels using a rolling window.
3.  Merge nearby pivots into distinct zones (support or resistance).
4.  On each scan, the latest CLOSED candle must pass ALL 6 gates:
      Gate 1 — Zone gap: nearest S and R must be far enough apart.
      Gate 2 — Zone touch: candle high/low reaches into the nearest zone.
      Gate 3 — Strong body: body ≥ 30% of the full candle range.
      Gate 4 — Escaped zone: close is fully outside the touched zone.
      Gate 5 — Reversal pattern: pin-bar (wick ≥ 1.5× body) or engulfing.
      Gate 6 — Momentum: close moved ≥ 0.02% of price away from zone.
5.  Emit a signal only when ALL gates pass and the signal is fresh
    (signature-gated so the same bar is not traded twice).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import logging

import pandas as pd
import numpy as np

from base_strategy import BaseStrategy
from risefallbot import rf_config

logger = logging.getLogger("risefallbot.strategy")


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers (identical pattern to the original strategy)
# ─────────────────────────────────────────────────────────────────────────────

def _cfg_value(name: str, default):
    cfg_dict = getattr(rf_config, "__dict__", {})
    if isinstance(cfg_dict, dict) and name in cfg_dict:
        return cfg_dict[name]
    return default


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(_cfg_value(name, default))
    except (TypeError, ValueError):
        return default


def _cfg_float(name: str, default: float) -> float:
    try:
        return float(_cfg_value(name, default))
    except (TypeError, ValueError):
        return default


def _cfg_bool(name: str, default: bool) -> bool:
    value = _cfg_value(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default


# ─────────────────────────────────────────────────────────────────────────────
# Zone dataclass (plain dict for JSON-serialisability)
# ─────────────────────────────────────────────────────────────────────────────

def _make_zone(
    zone_type: str,   # "support" | "resistance"
    level: float,
    touches: int = 1,
    half_width: float = 0.0,
) -> Dict[str, Any]:
    return {
        "type": zone_type,
        "level": level,
        "touches": touches,
        "upper": level + half_width,
        "lower": level - half_width,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main strategy class
# ─────────────────────────────────────────────────────────────────────────────

class RiseFallStrategy(BaseStrategy):
    """
    R_25 Support & Resistance reversal strategy.

    Uses 1-minute OHLCV candles to:
      1. Build support/resistance zones from swing pivots.
      2. Detect when price touches a zone on the latest candle.
      3. Require a confirmation candle pattern (pin-bar or engulfing).
      4. Fire RISE at support, FALL at resistance.
    """

    def __init__(self):
        # ── allowed symbols ──────────────────────────────────────────────
        self.allowed_symbols: Tuple[str, ...] = tuple(
            _cfg_value("RF_SUPPORTED_SYMBOLS", _cfg_value("RF_SYMBOLS", []))
        )

        # ── S&R detection parameters ─────────────────────────────────────
        self.sr_candle_count         = _cfg_int("RF_SR_CANDLE_COUNT", 100)
        self.sr_pivot_window         = _cfg_int("RF_SR_PIVOT_WINDOW", 5)
        self.sr_merge_pct            = _cfg_float("RF_SR_MERGE_PCT", 0.10)
        self.sr_zone_touch_buffer_pct = _cfg_float("RF_SR_ZONE_TOUCH_BUFFER_PCT", 0.05)
        self.sr_max_zones            = _cfg_int("RF_SR_MAX_ZONES", 10)
        self.sr_min_touches          = _cfg_int("RF_SR_MIN_TOUCHES", 2)

        # ── confirmation candle parameters ───────────────────────────────
        self.confirm_wick_ratio           = _cfg_float("RF_CONFIRM_WICK_RATIO", 1.5)
        self.confirm_max_body_pct_of_zone = _cfg_float("RF_CONFIRM_MAX_BODY_PCT_OF_ZONE", 150.0)
        self.confirm_lookback             = _cfg_int("RF_CONFIRM_LOOKBACK", 1)

        # ── entry gate parameters ────────────────────────────────────────
        self.sr_min_zone_gap_pct      = _cfg_float("RF_SR_MIN_ZONE_GAP_PCT", 0.10)
        self.confirm_min_body_pct     = _cfg_float("RF_CONFIRM_MIN_BODY_PCT", 30.0)
        self.confirm_min_momentum_pct = _cfg_float("RF_CONFIRM_MIN_MOMENTUM_PCT", 0.02)

        # ── contract parameters ──────────────────────────────────────────
        self.default_stake    = _cfg_float("RF_DEFAULT_STAKE", 1.0)
        self.duration         = _cfg_int("RF_CONTRACT_DURATION", 2)
        self.duration_unit    = str(_cfg_value("RF_DURATION_UNIT", "m"))

        # ── freshness gate ───────────────────────────────────────────────
        # Maps symbol → last emitted signal signature so the same candle
        # cannot trigger two trades.
        self._last_signal_signature: Dict[str, str] = {}

        # ── analysis metadata ────────────────────────────────────────────
        self._last_analysis: Dict[str, Dict[str, Any]] = {}

    # ─────────────────────────────────────────────────────────────────────
    # Public helpers (kept compatible with rf_bot.py)
    # ─────────────────────────────────────────────────────────────────────

    def get_last_analysis(self, symbol: str) -> Dict[str, Any]:
        data = self._last_analysis.get(symbol, {})
        return dict(data) if isinstance(data, dict) else {}

    def get_required_timeframes(self) -> List[str]:
        return ["1m"]

    def get_strategy_name(self) -> str:
        return "RiseFall"

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    def _reject(
        self,
        symbol: str,
        code: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        logger.info("[RF][%s] No trade | code=%s reason=%s", symbol, code, reason)
        self._last_analysis[symbol] = {
            "decision": "no_trade",
            "reason": reason,
            "code": code,
            "details": details or {},
        }

    def _accept(
        self,
        symbol: str,
        code: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._last_analysis[symbol] = {
            "decision": "signal",
            "reason": reason,
            "code": code,
            "details": details or {},
        }

    # ── Candle normalisation ─────────────────────────────────────────────

    def _normalize_candles(self, raw: Any) -> pd.DataFrame:
        """
        Accept a DataFrame or list-of-dicts with OHLCV columns.
        Returns a clean DataFrame with columns:
          open, high, low, close, volume (optional), timestamp, datetime
        Sorted oldest-first.
        """
        if raw is None:
            return pd.DataFrame()

        df = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        if df.empty:
            return df

        # ── map common alternative column names ──
        rename = {}
        for col in df.columns:
            lc = col.lower()
            if lc in ("open", "o") and "open" not in rename.values():
                rename[col] = "open"
            elif lc in ("high", "h") and "high" not in rename.values():
                rename[col] = "high"
            elif lc in ("low", "l") and "low" not in rename.values():
                rename[col] = "low"
            elif lc in ("close", "c", "quote", "price") and "close" not in rename.values():
                rename[col] = "close"
            elif lc in ("volume", "vol", "v") and "volume" not in rename.values():
                rename[col] = "volume"
            elif lc in ("epoch", "timestamp", "time") and "timestamp" not in rename.values():
                rename[col] = "timestamp"
        df = df.rename(columns=rename)

        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            logger.warning(
                "[RF-Strategy] Candle DataFrame missing columns: %s",
                required - set(df.columns),
            )
            return pd.DataFrame()

        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

        if "timestamp" not in df.columns:
            df["timestamp"] = range(len(df))
        else:
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")

        if "datetime" not in df.columns:
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    # ── Pivot detection ──────────────────────────────────────────────────

    def _find_pivots(
        self, df: pd.DataFrame
    ) -> Tuple[List[float], List[float]]:
        """
        Returns (swing_highs, swing_lows) as lists of price levels.
        A swing-high at index i: df['high'][i] is the max over
        [i-window … i+window].  Swing-lows are symmetric on 'low'.
        """
        w = self.sr_pivot_window
        highs: List[float] = []
        lows:  List[float] = []

        for i in range(w, len(df) - w):
            h = float(df["high"].iloc[i])
            l = float(df["low"].iloc[i])

            left_h  = df["high"].iloc[i - w: i]
            right_h = df["high"].iloc[i + 1: i + w + 1]
            if h >= left_h.max() and h >= right_h.max():
                highs.append(h)

            left_l  = df["low"].iloc[i - w: i]
            right_l = df["low"].iloc[i + 1: i + w + 1]
            if l <= left_l.min() and l <= right_l.min():
                lows.append(l)

        return highs, lows

    # ── Zone building ────────────────────────────────────────────────────

    def _build_zones(
        self,
        df: pd.DataFrame,
        swing_highs: List[float],
        swing_lows:  List[float],
    ) -> List[Dict[str, Any]]:
        """
        Merge nearby pivot levels into zones and count their touches.

        Returns a list of zone dicts sorted by |distance from current price|.
        """
        if df.empty:
            return []

        current_price = float(df["close"].iloc[-1])
        merge_threshold = current_price * self.sr_merge_pct / 100.0

        def _merge_levels(levels: List[float]) -> List[Tuple[float, int]]:
            """Group levels within merge_threshold → (mean_level, count)."""
            if not levels:
                return []
            sorted_levels = sorted(levels)
            groups: List[List[float]] = [[sorted_levels[0]]]
            for lvl in sorted_levels[1:]:
                if lvl - groups[-1][-1] <= merge_threshold:
                    groups[-1].append(lvl)
                else:
                    groups.append([lvl])
            return [(float(np.mean(g)), len(g)) for g in groups]

        merged_highs = _merge_levels(swing_highs)
        merged_lows  = _merge_levels(swing_lows)

        # Count actual candle touches for each zone
        def _count_touches(level: float, df: pd.DataFrame, zone_type: str) -> int:
            half_buf = level * self.sr_zone_touch_buffer_pct / 100.0
            upper = level + half_buf
            lower = level - half_buf
            if zone_type == "resistance":
                return int(((df["high"] >= lower) & (df["high"] <= upper * 1.002)).sum())
            else:
                return int(((df["low"] >= lower * 0.998) & (df["low"] <= upper)).sum())

        half_buf = current_price * self.sr_zone_touch_buffer_pct / 100.0

        zones: List[Dict[str, Any]] = []
        for level, pivot_count in merged_highs:
            touches = _count_touches(level, df, "resistance")
            total   = pivot_count + touches
            if total >= self.sr_min_touches:
                zones.append(_make_zone("resistance", level, total, half_buf))

        for level, pivot_count in merged_lows:
            touches = _count_touches(level, df, "support")
            total   = pivot_count + touches
            if total >= self.sr_min_touches:
                zones.append(_make_zone("support", level, total, half_buf))

        # Sort by strength (touches) descending, then trim to max_zones
        zones.sort(key=lambda z: -z["touches"])
        zones = zones[: self.sr_max_zones]

        # Re-sort by distance from current price (nearest first) for signal logic
        zones.sort(key=lambda z: abs(z["level"] - current_price))
        return zones

    # ── Zone touch detection ─────────────────────────────────────────────

    def _candle_touches_zone(
        self, candle: pd.Series, zone: Dict[str, Any]
    ) -> bool:
        """
        Returns True if the candle's high or low enters the zone's buffer.
        """
        upper = zone["upper"]
        lower = zone["lower"]

        if zone["type"] == "resistance":
            # High must reach up into the resistance zone
            return float(candle["high"]) >= lower and float(candle["low"]) <= upper
        else:
            # Low must dip into the support zone
            return float(candle["low"]) <= upper and float(candle["high"]) >= lower

    # ── Confirmation candle patterns ─────────────────────────────────────

    def _is_bullish_pin_bar(self, candle: pd.Series, zone: Dict[str, Any]) -> bool:
        """
        Bullish pin-bar: long lower wick, small body near the top of the candle.
        Lower wick ≥ confirm_wick_ratio × body.
        Candle close should be in upper half of candle range.
        """
        o = float(candle["open"])
        h = float(candle["high"])
        l = float(candle["low"])
        c = float(candle["close"])

        body        = abs(c - o)
        full_range  = h - l
        lower_wick  = min(o, c) - l
        upper_wick  = h - max(o, c)

        if full_range == 0:
            return False

        # Lower wick dominates
        if body > 0 and lower_wick < self.confirm_wick_ratio * body:
            return False
        # Close in upper half of range
        if c < l + full_range * 0.5:
            return False
        # Lower wick should be larger than upper wick
        if lower_wick <= upper_wick:
            return False
        return True

    def _is_bearish_pin_bar(self, candle: pd.Series, zone: Dict[str, Any]) -> bool:
        """
        Bearish pin-bar: long upper wick, small body near the bottom of the candle.
        Upper wick ≥ confirm_wick_ratio × body.
        """
        o = float(candle["open"])
        h = float(candle["high"])
        l = float(candle["low"])
        c = float(candle["close"])

        body        = abs(c - o)
        full_range  = h - l
        upper_wick  = h - max(o, c)
        lower_wick  = min(o, c) - l

        if full_range == 0:
            return False

        if body > 0 and upper_wick < self.confirm_wick_ratio * body:
            return False
        if c > l + full_range * 0.5:
            return False
        if upper_wick <= lower_wick:
            return False
        return True

    def _is_bullish_engulf(
        self, prev: pd.Series, curr: pd.Series
    ) -> bool:
        """Bullish engulfing: previous candle bearish, current bullish and wraps it."""
        prev_bearish = float(prev["close"]) < float(prev["open"])
        curr_bullish = float(curr["close"]) > float(curr["open"])
        engulfs = (
            float(curr["open"]) <= float(prev["close"])
            and float(curr["close"]) >= float(prev["open"])
        )
        return prev_bearish and curr_bullish and engulfs

    def _is_bearish_engulf(
        self, prev: pd.Series, curr: pd.Series
    ) -> bool:
        """Bearish engulfing: previous candle bullish, current bearish and wraps it."""
        prev_bullish = float(prev["close"]) > float(prev["open"])
        curr_bearish = float(curr["close"]) < float(curr["open"])
        engulfs = (
            float(curr["open"]) >= float(prev["close"])
            and float(curr["close"]) <= float(prev["open"])
        )
        return prev_bullish and curr_bearish and engulfs

    # ── Gate helpers (6-gate entry model) ───────────────────────────────

    @staticmethod
    def _find_nearest_sr_pair(
        zones: List[Dict[str, Any]], price: float
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Return (nearest_support, nearest_resistance) relative to *price*."""
        nearest_sup: Optional[Dict[str, Any]] = None
        nearest_res: Optional[Dict[str, Any]] = None
        best_sup_dist = float("inf")
        best_res_dist = float("inf")
        for z in zones:
            dist = abs(z["level"] - price)
            if z["type"] == "support" and dist < best_sup_dist:
                nearest_sup = z
                best_sup_dist = dist
            elif z["type"] == "resistance" and dist < best_res_dist:
                nearest_res = z
                best_res_dist = dist
        return nearest_sup, nearest_res

    def _check_zone_gap(
        self,
        support: Optional[Dict[str, Any]],
        resistance: Optional[Dict[str, Any]],
        price: float,
    ) -> bool:
        """Gate 1 — True when the S/R gap is wide enough for a reversal."""
        if support is None or resistance is None:
            return True  # only one side exists; gap is infinite
        gap_pct = abs(resistance["level"] - support["level"]) / price * 100
        return gap_pct >= self.sr_min_zone_gap_pct

    def _check_strong_body(self, candle: pd.Series) -> bool:
        """Gate 3 — True when candle body is ≥ confirm_min_body_pct of range."""
        h = float(candle["high"])
        l = float(candle["low"])
        full_range = h - l
        if full_range == 0:
            return False
        body = abs(float(candle["close"]) - float(candle["open"]))
        return (body / full_range) * 100 >= self.confirm_min_body_pct

    def _check_escaped_zone(
        self, candle: pd.Series, zone: Dict[str, Any]
    ) -> bool:
        """Gate 4 — True when the close is fully outside the zone."""
        close = float(candle["close"])
        if zone["type"] == "resistance":
            return close < zone["lower"]
        else:  # support
            return close > zone["upper"]

    def _check_momentum(
        self, candle: pd.Series, zone: Dict[str, Any], price: float
    ) -> bool:
        """Gate 6 — True when close has moved far enough away from the zone."""
        close = float(candle["close"])
        if zone["type"] == "resistance":
            distance = zone["lower"] - close  # close below zone
        else:  # support
            distance = close - zone["upper"]  # close above zone
        min_distance = price * self.confirm_min_momentum_pct / 100.0
        return distance >= min_distance

    # ── Confirmation candle patterns (Gate 5) ────────────────────────────

    def _confirmation_for_zone(
        self,
        df: pd.DataFrame,
        zone: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Checks the last `confirm_lookback` closed candles for a valid
        confirmation pattern at the given zone.

        Returns (confirmed: bool, pattern_name: str).
        """
        n = len(df)
        if n < 2:
            return False, ""

        # The most recent closed candle is df.iloc[-1]
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        if zone["type"] == "support":
            if self._is_bullish_pin_bar(curr, zone):
                return True, "bullish_pin_bar"
            if self._is_bullish_engulf(prev, curr):
                return True, "bullish_engulf"
        else:  # resistance
            if self._is_bearish_pin_bar(curr, zone):
                return True, "bearish_pin_bar"
            if self._is_bearish_engulf(prev, curr):
                return True, "bearish_engulf"

        return False, ""

    # ── Signal signature ─────────────────────────────────────────────────

    @staticmethod
    def _signal_signature(
        symbol: str,
        zone_type: str,
        zone_level: float,
        candle_timestamp: float,
    ) -> str:
        return f"{symbol}:{zone_type}:{zone_level:.5f}:{candle_timestamp:.0f}"

    # ─────────────────────────────────────────────────────────────────────
    # Primary entry point: analyze()
    # Called by rf_bot._process_symbol() — must accept **kwargs and return
    # a signal dict or None (same contract as the original strategy).
    # ─────────────────────────────────────────────────────────────────────

    def analyze(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Analyse the latest 1-minute candles for R_25 and return a signal dict
        if an S&R zone touch + confirmation candle is detected.

        Expected kwargs
        ---------------
        data_1m   : DataFrame or list-of-dicts with 1-minute OHLCV candles
        symbol    : trading symbol (default "R_25")
        stake     : trade stake (default self.default_stake)
        """
        symbol = kwargs.get("symbol", "R_25")
        stake  = kwargs.get("stake",  self.default_stake)

        # Accept both key names for backward-compat with rf_bot.py
        raw_candles = kwargs.get("data_1m")
        if raw_candles is None:
            raw_candles = kwargs.get("data_ticks")

        # ── symbol whitelist ─────────────────────────────────────────────
        if self.allowed_symbols and symbol not in self.allowed_symbols:
            self._reject(
                symbol, "symbol_not_allowed", "Symbol not in allowed list",
                {"allowed": list(self.allowed_symbols)},
            )
            return None

        # ── normalise candles ────────────────────────────────────────────
        df = self._normalize_candles(raw_candles)

        min_required = self.sr_candle_count
        if df.empty or len(df) < min_required:
            self._reject(
                symbol, "insufficient_candle_history",
                f"Need {min_required} candles, got {len(df)}",
                {"candles_available": len(df), "candles_required": min_required},
            )
            return None

        # Use only the last sr_candle_count candles for S&R calculation
        df = df.tail(self.sr_candle_count).reset_index(drop=True)
        current_price = float(df["close"].iloc[-1])

        # ── build S&R zones ──────────────────────────────────────────────
        swing_highs, swing_lows = self._find_pivots(df)
        zones = self._build_zones(df, swing_highs, swing_lows)

        if not zones:
            self._reject(
                symbol, "no_zones_detected",
                "No valid S&R zones found in candle history",
                {
                    "candles": len(df),
                    "swing_highs": len(swing_highs),
                    "swing_lows": len(swing_lows),
                },
            )
            return None

        # ── identify nearest support / resistance pair ────────────────────
        latest_candle = df.iloc[-1]
        latest_ts     = float(latest_candle["timestamp"])

        nearest_sup, nearest_res = self._find_nearest_sr_pair(
            zones, current_price
        )

        # ── Gate 1 — zone gap filter ────────────────────────────────────
        if not self._check_zone_gap(nearest_sup, nearest_res, current_price):
            self._reject(
                symbol, "zone_gap_too_narrow",
                "Nearest S and R zones are too close together",
                {
                    "support_level": nearest_sup["level"] if nearest_sup else None,
                    "resistance_level": nearest_res["level"] if nearest_res else None,
                    "min_gap_pct": self.sr_min_zone_gap_pct,
                },
            )
            return None

        # ── Gates 2-6: evaluate each candidate zone ─────────────────────
        candidates = [z for z in (nearest_sup, nearest_res) if z is not None]
        touched_zone  = None
        pattern_name  = ""
        last_reject_code   = "no_zone_touch"
        last_reject_reason = "Latest candle does not touch any active S&R zone"

        for zone in candidates:
            # Gate 2 — zone touch
            if not self._candle_touches_zone(latest_candle, zone):
                continue
            last_reject_code = "no_zone_touch"

            # Gate 3 — strong body close
            if not self._check_strong_body(latest_candle):
                last_reject_code = "weak_body"
                last_reject_reason = (
                    f"Candle body too small at "
                    f"{zone['type']} zone {zone['level']:.5f}"
                )
                continue

            # Gate 4 — escaped the zone
            if not self._check_escaped_zone(latest_candle, zone):
                last_reject_code = "close_inside_zone"
                last_reject_reason = (
                    f"Close still inside {zone['type']} zone "
                    f"{zone['level']:.5f}"
                )
                continue

            # Gate 5 — reversal pattern
            conf, pat = self._confirmation_for_zone(df, zone)
            if not conf:
                last_reject_code = "no_confirmation_candle"
                last_reject_reason = (
                    f"Zone touched ({zone['type']} @ {zone['level']:.5f}) "
                    "but no confirmation candle pattern found"
                )
                continue

            # Gate 6 — momentum filter
            if not self._check_momentum(latest_candle, zone, current_price):
                last_reject_code = "insufficient_momentum"
                last_reject_reason = (
                    f"Close lacks momentum away from "
                    f"{zone['type']} zone {zone['level']:.5f}"
                )
                continue

            # All 6 gates passed
            touched_zone = zone
            pattern_name = pat
            break

        if touched_zone is None:
            near_zones = [
                {"type": z["type"], "level": round(z["level"], 5), "touches": z["touches"]}
                for z in zones[:5]
            ]
            self._reject(
                symbol, last_reject_code, last_reject_reason,
                {
                    "current_price": current_price,
                    "zones_detected": len(zones),
                    "nearest_zones": near_zones,
                },
            )
            return None

        # ── determine trade direction ────────────────────────────────────
        if touched_zone["type"] == "support":
            contract_direction = "CALL"
            trade_label        = "RISE"
            sequence_direction = "up"
        else:
            contract_direction = "PUT"
            trade_label        = "FALL"
            sequence_direction = "down"

        # ── freshness gate ───────────────────────────────────────────────
        sig = self._signal_signature(
            symbol,
            touched_zone["type"],
            touched_zone["level"],
            latest_ts,
        )
        if self._last_signal_signature.get(symbol) == sig:
            self._reject(
                symbol, "signal_not_fresh",
                "Signal already emitted for this candle + zone combination",
                {"signature": sig},
            )
            return None

        self._last_signal_signature[symbol] = sig

        # ── build signal dict ────────────────────────────────────────────
        candle_dt = latest_candle.get("datetime")
        candle_dt_iso = (
            candle_dt.isoformat()
            if hasattr(candle_dt, "isoformat")
            else str(candle_dt)
        )

        signal: Dict[str, Any] = {
            "symbol":              symbol,
            "direction":           contract_direction,
            "trade_label":         trade_label,
            "sequence_direction":  sequence_direction,
            "stake":               stake,
            "duration":            self.duration,
            "duration_unit":       self.duration_unit,
            # Zone info
            "zone_type":           touched_zone["type"],
            "zone_level":          round(touched_zone["level"], 5),
            "zone_upper":          round(touched_zone["upper"],  5),
            "zone_lower":          round(touched_zone["lower"],  5),
            "zone_touches":        touched_zone["touches"],
            # Pattern
            "confirmation_pattern": pattern_name,
            # Candle snapshot
            "candle_open":         round(float(latest_candle["open"]),  5),
            "candle_high":         round(float(latest_candle["high"]),  5),
            "candle_low":          round(float(latest_candle["low"]),   5),
            "candle_close":        round(float(latest_candle["close"]), 5),
            "candle_timestamp":    latest_ts,
            "candle_datetime":     candle_dt_iso,
            # Meta
            "sequence_signature":  sig,
            "sequence_started_at": candle_dt_iso,
            "sequence_ended_at":   candle_dt_iso,
            "sequence_start_epoch": latest_ts,
            "sequence_end_epoch":   latest_ts,
            "confidence":           min(10, touched_zone["touches"]),
        }

        logger.info(
            "[RF][%s] Signal: %s @ %s zone (level=%.5f) | pattern=%s | "
            "entry=%s duration=%s%s",
            symbol,
            trade_label,
            touched_zone["type"],
            touched_zone["level"],
            pattern_name,
            contract_direction,
            self.duration,
            self.duration_unit,
        )

        self._accept(
            symbol,
            code="signal_ready",
            reason=f"{trade_label} signal at {touched_zone['type']} zone",
            details={
                "direction":            contract_direction,
                "trade_label":          trade_label,
                "zone_type":            touched_zone["type"],
                "zone_level":           touched_zone["level"],
                "confirmation_pattern": pattern_name,
            },
        )
        return signal