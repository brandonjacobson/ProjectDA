"""Polymarket CLOB WebSocket feed — order book events with reconnect logic."""
import asyncio
import json
import logging
import time
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-live-data.polymarket.com"
MAX_RECONNECT_DELAY = 60  # seconds
INITIAL_RECONNECT_DELAY = 1


class PolymarketFeed:
    """Streams real-time order book events from Polymarket CLOB WebSocket."""

    def __init__(
        self,
        token_ids: list[str],
        on_book_update: Optional[Callable] = None,
        on_price_change: Optional[Callable] = None,
    ):
        self.token_ids = token_ids
        self.on_book_update = on_book_update
        self.on_price_change = on_price_change
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = INITIAL_RECONNECT_DELAY
        # Latest mid price per token_id
        self.prices: dict[str, float] = {}
        self.last_update: dict[str, float] = {}

    async def connect(self) -> None:
        """Connect and subscribe to order book channels."""
        logger.info(f"Connecting to Polymarket WS for {len(self.token_ids)} tokens")
        self._ws = await websockets.connect(WS_URL, ping_interval=20, ping_timeout=20)
        # Subscribe to order book updates
        sub_msg = {
            "auth": {},
            "type": "subscribe",
            "channel": "live_activity_feed",
            "markets": self.token_ids,
        }
        await self._ws.send(json.dumps(sub_msg))
        logger.info("Subscribed to Polymarket order book feed")
        self._reconnect_delay = INITIAL_RECONNECT_DELAY  # reset on success

    async def _handle_message(self, raw: str) -> None:
        """Parse and dispatch a message from the WebSocket."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Non-JSON message: {raw[:100]}")
            return

        msg_type = msg.get("event_type") or msg.get("type", "")

        if msg_type == "book":
            token_id = msg.get("asset_id") or msg.get("market", "")
            bids = msg.get("bids", [])
            asks = msg.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0]["price"]) if bids else 0.0
                best_ask = float(asks[0]["price"]) if asks else 1.0
                mid = (best_bid + best_ask) / 2
                old_price = self.prices.get(token_id)
                self.prices[token_id] = mid
                self.last_update[token_id] = time.time()
                if self.on_book_update:
                    await self._safe_callback(
                        self.on_book_update,
                        token_id=token_id,
                        bids=bids,
                        asks=asks,
                        mid=mid,
                    )
                if old_price is not None and old_price != mid and self.on_price_change:
                    await self._safe_callback(
                        self.on_price_change,
                        token_id=token_id,
                        old_price=old_price,
                        new_price=mid,
                    )

        elif msg_type == "price_change":
            token_id = msg.get("asset_id", "")
            price = float(msg.get("price", 0))
            if token_id and price:
                self.prices[token_id] = price
                self.last_update[token_id] = time.time()

    @staticmethod
    async def _safe_callback(fn: Callable, **kwargs) -> None:
        try:
            result = fn(**kwargs)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Callback error in {fn.__name__}: {e}")

    async def run(self) -> None:
        """Run the feed with exponential backoff reconnection."""
        self._running = True
        while self._running:
            try:
                await self.connect()
                async for raw in self._ws:
                    if not self._running:
                        break
                    await self._handle_message(raw)
            except ConnectionClosed as e:
                logger.warning(f"Polymarket WS closed: {e} — reconnecting in {self._reconnect_delay}s")
            except Exception as e:
                logger.error(f"Polymarket WS error: {e} — reconnecting in {self._reconnect_delay}s")
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
        logger.info("PolymarketFeed stopped")

    def get_price(self, token_id: str) -> Optional[float]:
        return self.prices.get(token_id)
