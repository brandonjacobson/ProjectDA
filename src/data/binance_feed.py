"""Binance.US WebSocket feed — real-time BTC/ETH/SOL spot prices.

Uses one independent WebSocket connection per symbol so a silent
stream failure on one asset does not starve the others.

Stream type: @bookTicker (fires on every best bid/ask change)
  - Chosen over @trade because Binance.US has very low trade volume
    (BTC/ETH/SOL can go many minutes between actual trades).
  - @bookTicker fires on quote changes, giving continuous price updates
    even on low-volume pairs.
  - Mid = (best_bid + best_ask) / 2 is used as the mark price.
  - Message format: {"s":"BTCUSDT","b":"70717.44","B":"0.1","a":"70760.27","A":"0.5"}
    (no "e" event field — pure quote update)
"""
import asyncio
import json
import logging
import time
from collections import deque
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.us:9443/ws"
MAX_RECONNECT_DELAY = 60
INITIAL_RECONNECT_DELAY = 1
# Keep enough history to cover the 60s lookback even when bookTicker fires rapidly.
# At ~10 updates/sec for ETH, 7200 entries ≈ 12 min of data.
PRICE_HISTORY_LEN = 7200


class BinanceFeed:
    """Streams real-time spot prices for BTC/ETH/SOL from Binance.US via @bookTicker.

    One WebSocket connection is maintained per symbol.  If any single
    stream drops, only that symbol reconnects — the others keep running.
    """

    # bookTicker fires on any best-bid/ask change — much more frequent than @trade
    STREAMS = {
        "BTC": "btcusdt@bookTicker",
        "ETH": "ethusdt@bookTicker",
        "SOL": "solusdt@bookTicker",
    }

    def __init__(
        self,
        symbols: list[str] = None,
        on_price: Optional[Callable] = None,
    ):
        self.symbols = symbols or list(self.STREAMS.keys())
        self.on_price = on_price
        self._running = False
        # Latest mid price per symbol
        self.prices: dict[str, float] = {}
        self.last_update: dict[str, float] = {}
        # Price history: symbol -> deque of (timestamp, mid_price)
        self.history: dict[str, deque] = {s: deque(maxlen=PRICE_HISTORY_LEN) for s in self.symbols}

    # ------------------------------------------------------------------
    # Per-symbol connection loop
    # ------------------------------------------------------------------

    async def _run_symbol(self, symbol: str) -> None:
        """Maintain a reconnecting WebSocket for a single symbol."""
        stream_name = self.STREAMS.get(symbol)
        if not stream_name:
            logger.error(f"No stream defined for symbol {symbol}")
            return

        url = f"{BINANCE_WS_BASE}/{stream_name}"
        reconnect_delay = INITIAL_RECONNECT_DELAY

        while self._running:
            ws = None
            try:
                logger.info(f"Connecting Binance.US {symbol} stream: {url}")
                ws = await websockets.connect(url, ping_interval=20, ping_timeout=20)
                reconnect_delay = INITIAL_RECONNECT_DELAY  # reset on success
                logger.info(f"Binance.US {symbol} bookTicker connected")

                async for raw in ws:
                    if not self._running:
                        break
                    await self._handle_quote(symbol, raw)

            except ConnectionClosed as e:
                logger.warning(
                    f"Binance.US {symbol} WS closed: {e} — "
                    f"reconnecting in {reconnect_delay}s"
                )
            except Exception as e:
                logger.error(
                    f"Binance.US {symbol} WS error: {e} — "
                    f"reconnecting in {reconnect_delay}s"
                )
            finally:
                if ws:
                    try:
                        await ws.close()
                    except Exception:
                        pass

            if self._running:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)

    async def _handle_quote(self, symbol: str, raw: str) -> None:
        """Parse a bookTicker message and update price history.

        bookTicker format (individual stream, no envelope):
          {"u":..., "s":"SOLUSDT", "b":"88.06", "B":"2.68", "a":"88.10", "A":"9.07"}
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        bid_str = data.get("b")
        ask_str = data.get("a")
        if bid_str is None or ask_str is None:
            return

        bid = float(bid_str)
        ask = float(ask_str)
        if bid <= 0 or ask <= 0 or bid >= ask:
            return

        mid = (bid + ask) / 2
        ts = time.time()

        self.prices[symbol] = mid
        self.last_update[symbol] = ts
        self.history[symbol].append((ts, mid))

        if self.on_price:
            await self._safe_callback(self.on_price, symbol=symbol, price=mid, ts=ts)

    @staticmethod
    async def _safe_callback(fn: Callable, **kwargs) -> None:
        try:
            result = fn(**kwargs)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"BinanceFeed callback error: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_price(self, symbol: str) -> Optional[float]:
        return self.prices.get(symbol)

    def get_price_change_pct(self, symbol: str, lookback_secs: int = 60) -> Optional[float]:
        """Return % price change over the last `lookback_secs` seconds.

        Requires at least one price point older than `lookback_secs` ago
        so that we're measuring actual movement, not a zero-window diff.
        """
        hist = self.history.get(symbol)
        if not hist:
            return None
        now = time.time()
        cutoff = now - lookback_secs
        # Find the oldest price that falls within the lookback window
        old_price: Optional[float] = None
        old_ts: Optional[float] = None
        for ts, price in hist:
            if ts >= cutoff:
                old_price = price
                old_ts = ts
                break
        current = self.prices.get(symbol)
        if old_price is None or current is None or old_price == 0:
            return None
        # Guard: if the baseline is too recent (< 5s old), we haven't
        # observed enough movement yet — return None to avoid noisy signals.
        if old_ts is not None and (now - old_ts) < 5:
            return None
        return (current - old_price) / old_price

    async def run(self) -> None:
        """Launch one independent connection task per symbol and await all."""
        self._running = True
        tasks = [
            asyncio.create_task(self._run_symbol(s), name=f"binance_{s}")
            for s in self.symbols
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        self._running = False
        logger.info("BinanceFeed stop requested")
