"""
Risk Engine — enforces position size limits, daily loss cap, and circuit breaker.
"""
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Risk controls:
    - Max position size: 2% of portfolio per trade
    - Daily loss cap: 5% of portfolio → kill switch
    - Max concurrent positions: 10
    - Circuit breaker: pause 1 hour after 3 consecutive losses
    """

    def __init__(
        self,
        portfolio_size: float = 1000.0,
        max_position_pct: float = 0.02,
        daily_loss_cap_pct: float = 0.05,
        max_concurrent: int = 10,
        circuit_breaker_losses: int = 3,
        circuit_breaker_pause_secs: int = 3600,
    ):
        self.portfolio_size = portfolio_size
        self.max_position_pct = max_position_pct
        self.daily_loss_cap_pct = daily_loss_cap_pct
        self.max_concurrent = max_concurrent
        self.circuit_breaker_losses = circuit_breaker_losses
        self.circuit_breaker_pause_secs = circuit_breaker_pause_secs

        self._kill_switch: bool = False
        self._kill_reason: str = ""
        self._circuit_breaker_until: float = 0.0
        self._consecutive_losses: int = 0
        self._on_kill_switch_callbacks: list = []

    # --- Public API ---

    def check_trade(
        self,
        open_position_count: int,
        daily_pnl: float,
        size: Optional[float] = None,
    ) -> tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str).
        Call before placing any order.
        """
        if self._kill_switch:
            return False, f"Kill switch active: {self._kill_reason}"

        if self.is_circuit_breaker_active():
            remaining = int(self._circuit_breaker_until - time.time())
            return False, f"Circuit breaker active — {remaining}s remaining"

        if open_position_count >= self.max_concurrent:
            return False, f"Max concurrent positions reached ({self.max_concurrent})"

        daily_loss = abs(min(daily_pnl, 0))
        daily_loss_cap = self.portfolio_size * self.daily_loss_cap_pct
        if daily_loss >= daily_loss_cap:
            self.trigger_kill_switch(f"Daily loss cap hit: ${daily_loss:.2f} >= ${daily_loss_cap:.2f}")
            return False, self._kill_reason

        if size is not None and size > self.max_position_size:
            return False, f"Position size ${size:.2f} exceeds max ${self.max_position_size:.2f}"

        return True, "ok"

    def calculate_position_size(self, confidence: float = 1.0) -> float:
        """Kelly-scaled position size capped at max_position_pct."""
        base = self.portfolio_size * self.max_position_pct
        return round(base * min(confidence, 1.0), 2)

    def record_trade_result(self, pnl: float) -> None:
        """Call after each trade closes to update circuit breaker state."""
        if pnl < 0:
            self._consecutive_losses += 1
            logger.info(f"Consecutive losses: {self._consecutive_losses}")
            if self._consecutive_losses >= self.circuit_breaker_losses:
                self._trigger_circuit_breaker()
        else:
            self._consecutive_losses = 0

    def trigger_kill_switch(self, reason: str) -> None:
        if not self._kill_switch:
            self._kill_switch = True
            self._kill_reason = reason
            logger.critical(f"KILL SWITCH TRIGGERED: {reason}")
            for cb in self._on_kill_switch_callbacks:
                try:
                    result = cb(reason)
                    if asyncio.iscoroutine(result):
                        asyncio.create_task(result)
                except Exception as e:
                    logger.error(f"Kill switch callback error: {e}")

    def reset_kill_switch(self) -> None:
        self._kill_switch = False
        self._kill_reason = ""
        logger.warning("Kill switch RESET manually")

    def is_circuit_breaker_active(self) -> bool:
        return time.time() < self._circuit_breaker_until

    def on_kill_switch(self, callback) -> None:
        """Register a callback to be called when kill switch triggers."""
        self._on_kill_switch_callbacks.append(callback)

    # --- Properties ---

    @property
    def max_position_size(self) -> float:
        return self.portfolio_size * self.max_position_pct

    @property
    def daily_loss_cap(self) -> float:
        return self.portfolio_size * self.daily_loss_cap_pct

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    @property
    def kill_reason(self) -> str:
        return self._kill_reason

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    # --- Private ---

    def _trigger_circuit_breaker(self) -> None:
        self._circuit_breaker_until = time.time() + self.circuit_breaker_pause_secs
        resume_at = time.strftime("%H:%M:%S", time.localtime(self._circuit_breaker_until))
        logger.warning(
            f"Circuit breaker triggered after {self._consecutive_losses} losses. "
            f"Pausing until {resume_at}"
        )
        self._consecutive_losses = 0
