"""
Shadow Mode Logger

Tracks signals that were REJECTED by confidence or entry-price filters,
simulates what would have happened if they had been traded, and appends
a result row to trades/shadow_trades.csv once each hypothetical position
reaches its take-profit or stop-loss.

Exit rules mirror the live bot:
  - Take profit : current Polymarket mid >= 0.85
  - Stop loss   : (current_price - entry_price) / entry_price <= -0.20

One CSV row is written per shadow position, appended when the position
closes (or at shutdown if still open, marked as "expired").
"""
import csv
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_CSV_HEADER = [
    "shadow_id",
    "symbol",
    "token_id",
    "direction",
    "filter_reason",
    "signal_ts",
    "binance_move_pct",
    "confidence",
    "fair_value",
    "edge",
    "entry_price",
    "exit_price",
    "exit_time",
    "exit_reason",
    "pnl_pct",
]

TAKE_PROFIT_THRESHOLD = 0.85
STOP_LOSS_PCT = -0.20


@dataclass
class ShadowPosition:
    shadow_id: str
    symbol: str
    token_id: str
    direction: str          # "up" or "down"
    filter_reason: str      # why the real trade was blocked
    signal_ts: float        # unix timestamp of the original signal

    # Signal details at time of rejection
    binance_move_pct: float
    confidence: Optional[float]   # None if rejected before confidence gate
    fair_value: Optional[float]   # None if rejected before edge gate
    edge: Optional[float]         # None if rejected before edge gate
    entry_price: float            # Polymarket mid at signal time

    # Tracking
    current_price: float = field(default=0.0)
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    exit_reason: Optional[str] = None
    closed: bool = False

    def __post_init__(self):
        self.current_price = self.entry_price

    @property
    def pnl_pct(self) -> Optional[float]:
        p = self.exit_price if self.exit_price is not None else self.current_price
        if not self.entry_price:
            return None
        return (p - self.entry_price) / self.entry_price


class ShadowLogger:
    """
    Creates and tracks hypothetical (shadow) positions from rejected signals.

    Usage in main.py:
        shadow_logger = ShadowLogger()

        # After strategy.evaluate() returns None:
        if self.strategy.last_shadow:
            shadow_logger.log_rejected_signal(self.strategy.last_shadow)

        # Inside _on_poly_book:
        shadow_logger.update_price(token_id, mid)

        # On shutdown:
        shadow_logger.expire_all()
    """

    def __init__(self, csv_path: str = "trades/shadow_trades.csv"):
        self._csv_path = csv_path
        self._positions: list[ShadowPosition] = []
        self._counter: int = 0
        # Dedup: token_id -> last minute-bucket (int(ts//60)) we logged a shadow entry
        self._last_logged_minute: dict[str, int] = {}
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        self._ensure_header()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_rejected_signal(self, shadow_info: dict) -> Optional[ShadowPosition]:
        """
        Create a shadow position from a rejected signal dict.

        Expected keys in shadow_info:
            symbol, token_id, direction, filter_reason,
            binance_move_pct, confidence (optional), fair_value (optional),
            edge (optional), poly_price

        At most one shadow entry is created per unique token_id per minute.
        Returns None (silently) if this market was already logged this minute.
        """
        ts = shadow_info.get("timestamp", time.time())
        token_id = shadow_info["token_id"]
        minute_bucket = int(ts // 60)
        if self._last_logged_minute.get(token_id) == minute_bucket:
            return None
        self._last_logged_minute[token_id] = minute_bucket
        self._counter += 1
        shadow_id = f"SHADOW-{int(ts)}-{self._counter:04d}"

        pos = ShadowPosition(
            shadow_id=shadow_id,
            symbol=shadow_info["symbol"],
            token_id=shadow_info["token_id"],
            direction=shadow_info["direction"],
            filter_reason=shadow_info["filter_reason"],
            signal_ts=ts,
            binance_move_pct=shadow_info["binance_move_pct"],
            confidence=shadow_info.get("confidence"),
            fair_value=shadow_info.get("fair_value"),
            edge=shadow_info.get("edge"),
            entry_price=shadow_info["poly_price"],
        )
        self._positions.append(pos)
        logger.info(
            f"[shadow] New shadow position {shadow_id}: {pos.symbol} {pos.direction.upper()} "
            f"@ {pos.entry_price:.4f} | rejected by: {pos.filter_reason} "
            f"| conf={pos.confidence} edge={pos.edge}"
        )
        return pos

    def update_price(self, token_id: str, mid: float) -> None:
        """
        Update all open shadow positions for this token and check exit conditions.
        Called from the Polymarket price feed callback.
        """
        for pos in self._positions:
            if pos.closed or pos.token_id != token_id:
                continue
            pos.current_price = mid

            if mid >= TAKE_PROFIT_THRESHOLD:
                self._close(pos, mid, "take_profit")
            elif pos.pnl_pct is not None and pos.pnl_pct <= STOP_LOSS_PCT:
                self._close(pos, mid, "stop_loss")

    def expire_all(self) -> None:
        """Mark all still-open shadow positions as expired (call on shutdown)."""
        for pos in self._positions:
            if not pos.closed:
                self._close(pos, pos.current_price, "expired")

    @property
    def open_count(self) -> int:
        return sum(1 for p in self._positions if not p.closed)

    @property
    def closed_positions(self) -> list[ShadowPosition]:
        return [p for p in self._positions if p.closed]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _close(self, pos: ShadowPosition, exit_price: float, reason: str) -> None:
        pos.exit_price = exit_price
        pos.exit_time = time.time()
        pos.exit_reason = reason
        pos.closed = True
        self._write_row(pos)
        pnl_str = f"{pos.pnl_pct:+.2%}" if pos.pnl_pct is not None else "N/A"
        logger.info(
            f"[shadow] Closed {pos.shadow_id}: {reason} @ {exit_price:.4f} | "
            f"pnl={pnl_str} (entered @ {pos.entry_price:.4f} | filter={pos.filter_reason})"
        )

    def _ensure_header(self) -> None:
        if not os.path.exists(self._csv_path):
            with open(self._csv_path, "w", newline="") as f:
                csv.writer(f).writerow(_CSV_HEADER)

    def _write_row(self, pos: ShadowPosition) -> None:
        row = [
            pos.shadow_id,
            pos.symbol,
            pos.token_id,
            pos.direction,
            pos.filter_reason,
            pos.signal_ts,
            pos.binance_move_pct,
            f"{pos.confidence:.4f}" if pos.confidence is not None else "",
            f"{pos.fair_value:.4f}" if pos.fair_value is not None else "",
            f"{pos.edge:.4f}" if pos.edge is not None else "",
            pos.entry_price,
            pos.exit_price if pos.exit_price is not None else "",
            pos.exit_time if pos.exit_time is not None else "",
            pos.exit_reason or "",
            f"{pos.pnl_pct:.6f}" if pos.pnl_pct is not None else "",
        ]
        with open(self._csv_path, "a", newline="") as f:
            csv.writer(f).writerow(row)
