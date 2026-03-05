"""
Order Manager — paper trading (default) and live mode.

Paper mode: logs trades to CSV, tracks positions and P&L in memory.
Live mode:  executes via py-clob-client.
"""
import asyncio
import csv
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from config.settings import ENTRY_PRICE_MIN, ENTRY_PRICE_MAX

logger = logging.getLogger(__name__)


@dataclass
class Position:
    token_id: str
    symbol: str
    direction: str
    size: float          # USDC notional
    entry_price: float
    entry_time: float = field(default_factory=time.time)
    current_price: float = 0.0
    closed: bool = False
    exit_price: float = 0.0
    exit_time: float = 0.0

    @property
    def pnl(self) -> float:
        price = self.exit_price if self.closed else self.current_price
        if price == 0 or self.entry_price == 0:
            return 0.0
        shares = self.size / self.entry_price
        return shares * (price - self.entry_price)

    @property
    def pnl_pct(self) -> float:
        if self.size == 0:
            return 0.0
        return self.pnl / self.size


@dataclass
class TradeRecord:
    trade_id: str
    token_id: str
    symbol: str
    direction: str
    side: str            # BUY / SELL
    size: float
    price: float
    timestamp: float
    paper: bool
    order_id: Optional[str] = None
    notes: str = ""


class OrderManager:
    """Manages order execution, position tracking, and P&L."""

    def __init__(
        self,
        paper_mode: bool = True,
        trades_dir: str = "trades",
        portfolio_size: float = 1000.0,
        clob_client=None,
    ):
        self.paper_mode = paper_mode
        self.trades_dir = trades_dir
        self.portfolio_size = portfolio_size
        self._clob_client = clob_client
        self.positions: dict[str, Position] = {}  # token_id -> Position
        self.closed_positions: list[Position] = []
        self._trade_counter = 0
        os.makedirs(trades_dir, exist_ok=True)
        self._csv_path = os.path.join(trades_dir, "paper_trades.csv")
        self._ensure_csv_header()

    def _ensure_csv_header(self) -> None:
        if not os.path.exists(self._csv_path):
            with open(self._csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "trade_id","token_id","symbol","direction","side",
                    "size","price","timestamp","paper","order_id","notes"
                ])
                w.writeheader()

    def _next_trade_id(self) -> str:
        self._trade_counter += 1
        return f"{'PAPER' if self.paper_mode else 'LIVE'}-{int(time.time())}-{self._trade_counter:04d}"

    async def place_order(
        self,
        token_id: str,
        symbol: str,
        direction: str,
        size: float,
        price: float,
        confidence: float = 0.0,
    ) -> Optional[TradeRecord]:
        """Place a BUY order (paper or live)."""
        if not (ENTRY_PRICE_MIN <= price <= ENTRY_PRICE_MAX):
            logger.warning(
                f"Order rejected — price {price:.4f} outside safe range "
                f"[{ENTRY_PRICE_MIN}, {ENTRY_PRICE_MAX}] for {symbol} {direction}"
            )
            return None

        if token_id in self.positions and not self.positions[token_id].closed:
            logger.warning(f"Already have open position for {token_id}")
            return None

        trade_id = self._next_trade_id()
        order_id = None

        if self.paper_mode:
            logger.info(f"[PAPER] BUY {symbol} {direction} | size=${size:.2f} @ {price:.4f} | conf={confidence:.2f}")
        else:
            try:
                order_id = await self._place_live_order(token_id, size, price)
                logger.info(f"[LIVE] Order placed: {order_id}")
            except Exception as e:
                logger.error(f"Live order failed: {e}")
                return None

        record = TradeRecord(
            trade_id=trade_id,
            token_id=token_id,
            symbol=symbol,
            direction=direction,
            side="BUY",
            size=size,
            price=price,
            timestamp=time.time(),
            paper=self.paper_mode,
            order_id=order_id,
            notes=f"conf={confidence:.2f}",
        )
        self._log_trade(record)

        pos = Position(
            token_id=token_id,
            symbol=symbol,
            direction=direction,
            size=size,
            entry_price=price,
            current_price=price,
        )
        self.positions[token_id] = pos
        return record

    async def close_position(
        self, token_id: str, exit_price: float, reason: str = ""
    ) -> Optional[TradeRecord]:
        pos = self.positions.get(token_id)
        if pos is None or pos.closed:
            return None

        trade_id = self._next_trade_id()
        order_id = None

        if not self.paper_mode:
            try:
                order_id = await self._place_live_order(token_id, pos.size, exit_price, side="SELL")
            except Exception as e:
                logger.error(f"Live close failed: {e}")
                return None

        pos.closed = True
        pos.exit_price = exit_price
        pos.exit_time = time.time()
        self.closed_positions.append(pos)
        del self.positions[token_id]

        record = TradeRecord(
            trade_id=trade_id,
            token_id=token_id,
            symbol=pos.symbol,
            direction=pos.direction,
            side="SELL",
            size=pos.size,
            price=exit_price,
            timestamp=time.time(),
            paper=self.paper_mode,
            order_id=order_id,
            notes=reason,
        )
        self._log_trade(record)
        pnl = pos.pnl
        logger.info(f"Closed {pos.symbol} {pos.direction} | PnL=${pnl:+.2f} ({pos.pnl_pct:+.2%}) | {reason}")
        return record

    async def _place_live_order(
        self, token_id: str, size: float, price: float, side: str = "BUY"
    ) -> str:
        """Execute real order via py-clob-client. Returns order_id."""
        if self._clob_client is None:
            raise RuntimeError("No clob_client configured for live trading")
        # py-clob-client integration
        from py_clob_client.order_builder.constants import BUY, SELL
        from py_clob_client.clob_types import OrderArgs
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY if side == "BUY" else SELL,
        )
        resp = self._clob_client.create_and_post_order(order_args)
        return resp.get("orderID", "unknown")

    def update_price(self, token_id: str, price: float) -> None:
        """Update current price for an open position."""
        pos = self.positions.get(token_id)
        if pos and not pos.closed:
            pos.current_price = price

    def _log_trade(self, record: TradeRecord) -> None:
        with open(self._csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "trade_id","token_id","symbol","direction","side",
                "size","price","timestamp","paper","order_id","notes"
            ])
            w.writerow(asdict(record))

    @property
    def open_positions(self) -> list[Position]:
        return list(self.positions.values())

    @property
    def total_pnl(self) -> float:
        closed = sum(p.pnl for p in self.closed_positions)
        open_ = sum(p.pnl for p in self.positions.values())
        return closed + open_

    @property
    def daily_pnl(self) -> float:
        """PnL from trades opened today."""
        today_start = time.time() - (time.time() % 86400)
        closed = sum(
            p.pnl for p in self.closed_positions
            if p.entry_time >= today_start
        )
        open_ = sum(
            p.pnl for p in self.positions.values()
            if p.entry_time >= today_start
        )
        return closed + open_

    @property
    def win_rate(self) -> float:
        if not self.closed_positions:
            return 0.0
        wins = sum(1 for p in self.closed_positions if p.pnl > 0)
        return wins / len(self.closed_positions)
