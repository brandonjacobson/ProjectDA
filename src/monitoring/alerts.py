"""Telegram alert integration — trade events, errors, daily summaries."""
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed; Telegram alerts disabled")


class AlertManager:
    """Sends Telegram messages for trade events, errors, and daily summaries."""

    def __init__(self, bot_token: str = "", chat_id: str = "", enabled: bool = True):
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id) and TELEGRAM_AVAILABLE
        self._bot: Optional["Bot"] = None
        if self.enabled:
            self._bot = Bot(token=bot_token)
        self._rate_limit_last: float = 0.0
        self._rate_limit_min_interval = 1.0  # max 1 msg/sec

    async def send(self, message: str, silent: bool = False) -> bool:
        """Send a message. Returns True on success."""
        if not self.enabled or not self._bot:
            logger.debug(f"[ALERT DISABLED] {message}")
            return False
        # Rate limiting
        now = time.time()
        elapsed = now - self._rate_limit_last
        if elapsed < self._rate_limit_min_interval:
            await asyncio.sleep(self._rate_limit_min_interval - elapsed)
        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown",
                disable_notification=silent,
            )
            self._rate_limit_last = time.time()
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def trade_opened(self, symbol: str, direction: str, size: float, price: float, confidence: float) -> None:
        emoji = "🟢" if direction == "up" else "🔴"
        msg = (
            f"{emoji} *Trade Opened*\n"
            f"`{symbol}` {direction.upper()} | "
            f"Size: `${size:.2f}` @ `{price:.4f}`\n"
            f"Confidence: `{confidence:.0%}`"
        )
        await self.send(msg)

    async def trade_closed(self, symbol: str, direction: str, pnl: float, pnl_pct: float, reason: str) -> None:
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} *Trade Closed*\n"
            f"`{symbol}` {direction.upper()} | "
            f"PnL: `${pnl:+.2f}` (`{pnl_pct:+.1%}`)\n"
            f"Reason: {reason}"
        )
        await self.send(msg)

    async def error(self, component: str, error_msg: str) -> None:
        msg = f"⚠️ *Error in {component}*\n```{error_msg[:400]}```"
        await self.send(msg)

    async def kill_switch(self, reason: str) -> None:
        msg = f"🚨 *KILL SWITCH ACTIVATED*\n{reason}"
        await self.send(msg, silent=False)

    async def daily_summary(
        self,
        total_pnl: float,
        daily_pnl: float,
        win_rate: float,
        trades_count: int,
        open_positions: int,
    ) -> None:
        status = "✅" if daily_pnl >= 0 else "📉"
        msg = (
            f"{status} *Daily Summary*\n"
            f"Daily PnL: `${daily_pnl:+.2f}`\n"
            f"Total PnL: `${total_pnl:+.2f}`\n"
            f"Win Rate: `{win_rate:.1%}` ({trades_count} trades)\n"
            f"Open Positions: `{open_positions}`"
        )
        await self.send(msg)

    async def circuit_breaker(self, consecutive_losses: int, pause_secs: int) -> None:
        msg = (
            f"⏸️ *Circuit Breaker*\n"
            f"{consecutive_losses} consecutive losses\n"
            f"Trading paused for {pause_secs // 60} minutes"
        )
        await self.send(msg)

    async def startup(self, paper_mode: bool, portfolio_size: float) -> None:
        mode = "📝 PAPER" if paper_mode else "💰 LIVE"
        msg = (
            f"🤖 *Bot Started* — {mode}\n"
            f"Portfolio: `${portfolio_size:.0f}`"
        )
        await self.send(msg)
