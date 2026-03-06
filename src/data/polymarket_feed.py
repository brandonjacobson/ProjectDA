"""Polymarket CLOB WebSocket feed — order book events with reconnect logic.

Key protocol notes (verified against official docs, 2026-03-05):
- WS URL:  wss://ws-subscriptions-clob.polymarket.com/ws/market
- Initial subscribe: {"assets_ids": [...], "type": "market"}   ← lowercase "market"
- Dynamic subscribe: {"assets_ids": [...], "operation": "subscribe"}
- Heartbeat: send "PING" string every 10 seconds (server closes if missed)
- Messages arrive as a JSON array (batch) or single dict.

Event types:
  "book"         — full order-book snapshot on subscribe.
                   bids[] and asks[] are NOT pre-sorted; sort before use:
                   bids descending (highest first), asks ascending (lowest first).
  "price_change" — incremental update.
                   asset_id / best_bid / best_ask live INSIDE price_changes[],
                   NOT at the top level of the message.
  "last_trade_price" — last executed trade price (fallback).
"""
import asyncio
import json
import logging
import time
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PING_INTERVAL = 10  # seconds — server drops connection if no PING received
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
        self._msg_count: int = 0

    # ------------------------------------------------------------------
    # Connection / subscription
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect and subscribe to order book channels."""
        logger.info(f"Connecting to Polymarket WS: {WS_URL} ({len(self.token_ids)} tokens)")
        # Disable websockets built-in ping — we send "PING" string manually per Polymarket protocol
        self._ws = await websockets.connect(WS_URL, ping_interval=None)
        if self.token_ids:
            # lowercase "type": "market" is required — uppercase "MARKET" returns INVALID OPERATION
            sub_msg = {"assets_ids": self.token_ids, "type": "market"}
            await self._ws.send(json.dumps(sub_msg))
            logger.info(f"Polymarket WS subscribed to {len(self.token_ids)} token(s)")
        self._reconnect_delay = INITIAL_RECONNECT_DELAY  # reset on success

    async def resubscribe(self) -> None:
        """Re-send subscription after token IDs change (e.g. market rotation)."""
        if self._ws and self.token_ids:
            try:
                # Dynamic subscribe without reconnecting uses "operation" key
                sub_msg = {"assets_ids": self.token_ids, "operation": "subscribe"}
                await self._ws.send(json.dumps(sub_msg))
                logger.info(f"Polymarket WS re-subscribed to {len(self.token_ids)} token(s)")
            except Exception as e:
                logger.warning(f"Resubscribe failed (reconnect will fix): {e}")

    async def _heartbeat(self) -> None:
        """Send PING every 10 seconds. Server closes connection if it stops."""
        try:
            while self._running and self._ws:
                await self._ws.send("PING")
                logger.debug("[POLY PING] sent")
                await asyncio.sleep(PING_INTERVAL)
        except Exception:
            pass  # connection closed; run loop will handle reconnect

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _handle_message(self, raw: str) -> None:
        """Parse and dispatch one raw WebSocket frame."""
        self._msg_count += 1
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Non-JSON WS frame: {raw[:120]}")
            return

        # Log first 5 raw frames at INFO so they appear in bot.log
        if self._msg_count <= 5:
            logger.info(f"Polymarket WS raw msg #{self._msg_count}: {raw[:400]}")

        if isinstance(msg, list):
            for item in msg:
                await self._process_event(item)
        else:
            await self._process_event(msg)

    async def _process_event(self, msg: dict) -> None:
        """Handle a single decoded event dict."""
        event_type = msg.get("event_type", "")

        # ---------------------------------------------------------------
        # book — full snapshot; bids/asks are unsorted, must sort first
        # ---------------------------------------------------------------
        if event_type == "book":
            token_id = msg.get("asset_id", "")
            raw_bids = msg.get("bids", [])
            raw_asks = msg.get("asks", [])

            if not token_id:
                return

            # Sort: bids descending (best = highest), asks ascending (best = lowest)
            bids = sorted(raw_bids, key=lambda x: float(x["price"]), reverse=True)
            asks = sorted(raw_asks, key=lambda x: float(x["price"]))

            if not bids or not asks:
                logger.warning(f"Empty book for token {token_id[:16]}… — skipping")
                return

            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            mid = (best_bid + best_ask) / 2

            old_price = self.prices.get(token_id)
            self.prices[token_id] = mid
            self.last_update[token_id] = time.time()

            logger.debug(
                f"[POLY BOOK] token={token_id[:16]}…  "
                f"bid={best_bid:.4f}  ask={best_ask:.4f}  mid={mid:.4f}  "
                f"(book depth: {len(bids)} bids / {len(asks)} asks)"
            )

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

        # ---------------------------------------------------------------
        # price_change — incremental update
        # asset_id / best_bid / best_ask are INSIDE price_changes[], not top-level
        # ---------------------------------------------------------------
        elif event_type == "price_change":
            price_changes = msg.get("price_changes", [])
            for pc in price_changes:
                token_id = pc.get("asset_id", "")
                if not token_id:
                    continue
                best_bid = float(pc.get("best_bid") or 0)
                best_ask = float(pc.get("best_ask") or 1)
                if best_bid <= 0 and best_ask >= 1:
                    # No valid quote in this update
                    continue
                mid = (best_bid + best_ask) / 2
                old_price = self.prices.get(token_id)
                self.prices[token_id] = mid
                self.last_update[token_id] = time.time()
                logger.debug(
                    f"[POLY TICK] token={token_id[:16]}…  "
                    f"bid={best_bid:.4f}  ask={best_ask:.4f}  mid={mid:.4f}"
                )
                # Evaluate stop-loss/take-profit on every tick (not just book snapshots)
                if self.on_book_update:
                    await self._safe_callback(
                        self.on_book_update,
                        token_id=token_id,
                        bids=[],
                        asks=[],
                        mid=mid,
                    )
                if old_price is not None and old_price != mid and self.on_price_change:
                    await self._safe_callback(
                        self.on_price_change,
                        token_id=token_id,
                        old_price=old_price,
                        new_price=mid,
                    )

        # ---------------------------------------------------------------
        # last_trade_price — seed only; don't overwrite a real book price
        # ---------------------------------------------------------------
        elif event_type == "last_trade_price":
            token_id = msg.get("asset_id", "")
            price = float(msg.get("price") or 0)
            if token_id and price and token_id not in self.prices:
                self.prices[token_id] = price
                self.last_update[token_id] = time.time()
                logger.debug(f"[POLY LTP] token={token_id[:16]}…  last_trade={price:.4f} (seeded)")

        elif event_type == "tick_size_change":
            pass  # informational

        else:
            if event_type:
                logger.debug(f"Unhandled Polymarket event_type={event_type!r}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe_callback(fn: Callable, **kwargs) -> None:
        try:
            result = fn(**kwargs)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Callback error in {fn.__name__}: {e}")

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the feed with exponential backoff reconnection."""
        self._running = True
        while self._running:
            ping_task = None
            try:
                await self.connect()
                ping_task = asyncio.create_task(self._heartbeat())
                async for raw in self._ws:
                    if not self._running:
                        break
                    await self._handle_message(raw)
            except ConnectionClosed as e:
                logger.warning(f"Polymarket WS closed: {e} — reconnecting in {self._reconnect_delay}s")
            except Exception as e:
                logger.error(f"Polymarket WS error: {e} — reconnecting in {self._reconnect_delay}s")
            finally:
                if ping_task:
                    ping_task.cancel()
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
