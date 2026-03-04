"""Binance WebSocket feed — real-time BTC/ETH/SOL spot prices."""
import asyncio
import json
import logging
import time
from collections import deque
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream"
MAX_RECONNECT_DELAY = 60
INITIAL_RECONNECT_DELAY = 1
PRICE_HISTORY_LEN = 120  # keep 2 minutes of ticks


class BinanceFeed:
    """Streams real-time spot prices for BTC/ETH/SOL from Binance."""

    STREAMS = {
        "BTC": "btcusdt@trade",
        "ETH": "ethusdt@trade",
        "SOL": "solusdt@trade",
    }

    def __init__(
        self,
        symbols: list[str] = None,
        on_price: Optional[Callable] = None,
    ):
        self.symbols = symbols or list(self.STREAMS.keys())
        self.on_price = on_price
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = INITIAL_RECONNECT_DELAY
        # Latest price per symbol
        self.prices: dict[str, float] = {}
        self.last_update: dict[str, float] = {}
        # Price history: symbol -> deque of (timestamp, price)
        self.history: dict[str, deque] = {s: deque(maxlen=PRICE_HISTORY_LEN) for s in self.symbols}

    def _build_url(self) -> str:
        streams = "/".join(self.STREAMS[s] for s in self.symbols if s in self.STREAMS)
        return f"{BINANCE_WS_BASE}?streams={streams}"

    async def connect(self) -> None:
        url = self._build_url()
        logger.info(f"Connecting to Binance WS: {url}")
        self._ws = await websockets.connect(url, ping_interval=20, ping_timeout=20)
        self._reconnect_delay = INITIAL_RECONNECT_DELAY
        logger.info(f"Connected to Binance WS for {self.symbols}")

    async def _handle_message(self, raw: str) -> None:
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            return

        data = envelope.get("data", {})
        stream = envelope.get("stream", "")
        event = data.get("e", "")

        if event == "trade":
            symbol_raw = data.get("s", "")  # e.g. "BTCUSDT"
            price = float(data.get("p", 0))
            ts = time.time()

            # Map back to short symbol
            symbol = symbol_raw.replace("USDT", "")
            if symbol in self.symbols and price > 0:
                self.prices[symbol] = price
                self.last_update[symbol] = ts
                self.history[symbol].append((ts, price))
                if self.on_price:
                    await self._safe_callback(self.on_price, symbol=symbol, price=price, ts=ts)

    @staticmethod
    async def _safe_callback(fn: Callable, **kwargs) -> None:
        try:
            result = fn(**kwargs)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"BinanceFeed callback error: {e}")

    def get_price(self, symbol: str) -> Optional[float]:
        return self.prices.get(symbol)

    def get_price_change_pct(self, symbol: str, lookback_secs: int = 60) -> Optional[float]:
        """Return % price change over the last `lookback_secs` seconds. None if insufficient data."""
        hist = self.history.get(symbol)
        if not hist:
            return None
        now = time.time()
        cutoff = now - lookback_secs
        # Find oldest price within window
        old_price = None
        for ts, price in hist:
            if ts >= cutoff:
                old_price = price
                break
        current = self.prices.get(symbol)
        if old_price is None or current is None or old_price == 0:
            return None
        return (current - old_price) / old_price

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.connect()
                async for raw in self._ws:
                    if not self._running:
                        break
                    await self._handle_message(raw)
            except ConnectionClosed as e:
                logger.warning(f"Binance WS closed: {e} — reconnecting in {self._reconnect_delay}s")
            except Exception as e:
                logger.error(f"Binance WS error: {e} — reconnecting in {self._reconnect_delay}s")
            finally:
                if self._ws:
                    await self._ws.close()
            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, MAX_RECONNECT_DELAY)

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
        logger.info("BinanceFeed stopped")
