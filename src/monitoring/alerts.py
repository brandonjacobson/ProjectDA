"""Telegram alert integration — trade events, errors, daily summaries.

Uses parse_mode='HTML' throughout. MarkdownV2 requires escaping +, -, (, ), .
and many other chars that appear naturally in financial messages.
"""
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
        """Send a plain-HTML message. Returns True on success."""
        if not self.enabled or not self._bot:
            logger.debug(f"[ALERT DISABLED] {message}")
            return False
        now = time.time()
        elapsed = now - self._rate_limit_last
        if elapsed < self._rate_limit_min_interval:
            await asyncio.sleep(self._rate_limit_min_interval - elapsed)
        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="HTML",
                disable_notification=silent,
            )
            self._rate_limit_last = time.time()
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Trade lifecycle
    # ------------------------------------------------------------------

    async def trade_opened(self, symbol: str, direction: str, size: float, price: float, confidence: float) -> None:
        emoji = "🟢" if direction == "up" else "🔴"
        msg = (
            f"{emoji} <b>Trade Opened</b>\n"
            f"<code>{symbol}</code> {direction.upper()} | "
            f"Size: <code>${size:.2f}</code> @ <code>{price:.4f}</code>\n"
            f"Confidence: <code>{confidence:.0%}</code>"
        )
        await self.send(msg)

    async def trade_closed(self, symbol: str, direction: str, pnl: float, pnl_pct: float, reason: str) -> None:
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} <b>Trade Closed</b>\n"
            f"<code>{symbol}</code> {direction.upper()} | "
            f"PnL: <code>${pnl:+.2f}</code> (<code>{pnl_pct:+.1%}</code>)\n"
            f"Reason: {reason}"
        )
        await self.send(msg)

    async def position_closed(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        reason: str,          # "take_profit" or "stop_loss"
        daily_pnl: float,
    ) -> None:
        """Detailed close alert — emitted by risk engine on TP/SL triggers."""
        if reason == "take_profit":
            emoji, label = "✅", "Take Profit"
        elif reason == "stop_loss":
            emoji, label = "🛑", "Stop Loss"
        else:
            emoji, label = ("✅" if pnl >= 0 else "❌"), reason.replace("_", " ").title()

        pnl_sign = "+" if pnl >= 0 else ""
        msg = (
            f"{emoji} <b>Position Closed — {label}</b>\n"
            f"<code>{symbol}</code> {direction.upper()}\n"
            f"Entry: <code>{entry_price:.4f}</code>  →  Exit: <code>{exit_price:.4f}</code>\n"
            f"PnL: <code>{pnl_sign}${pnl:.2f}</code> (<code>{pnl_pct:+.1%}</code>)\n"
            f"Daily PnL: <code>${daily_pnl:+.2f}</code>"
        )
        await self.send(msg)

    # ------------------------------------------------------------------
    # Periodic updates
    # ------------------------------------------------------------------

    async def periodic_update(
        self,
        daily_pnl: float,
        wins: int,
        losses: int,
        win_rate: float,
        portfolio_value: float,
        open_positions: list[dict],  # each: {symbol, direction, pnl}
    ) -> None:
        """2-hour summary: PnL, win/loss record, open positions."""
        status = "📈" if daily_pnl >= 0 else "📉"
        trades_total = wins + losses
        pos_lines = ""
        if open_positions:
            lines = []
            for p in open_positions:
                sign = "+" if p["pnl"] >= 0 else ""
                lines.append(
                    f"  • <code>{p['symbol']}</code> {p['direction'].upper()} "
                    f"<code>{sign}${p['pnl']:.2f}</code>"
                )
            pos_lines = "\nOpen Positions:\n" + "\n".join(lines)
        else:
            pos_lines = "\nOpen Positions: <code>none</code>"

        msg = (
            f"{status} <b>2-Hour Update</b>\n"
            f"Daily PnL: <code>${daily_pnl:+.2f}</code>\n"
            f"Trades: <code>{trades_total}</code> "
            f"(<code>{wins}W</code> / <code>{losses}L</code>)  "
            f"Win rate: <code>{win_rate:.1%}</code>\n"
            f"Portfolio: <code>${portfolio_value:,.2f}</code>"
            f"{pos_lines}"
        )
        await self.send(msg, silent=True)

    async def start_periodic_updates(
        self,
        interval_secs: int = 7200,
        get_stats_fn=None,
    ) -> None:
        """Run periodic_update every interval_secs. Pass a callable that returns
        the kwargs dict for periodic_update, or call periodic_update directly."""
        while True:
            await asyncio.sleep(interval_secs)
            if get_stats_fn is not None:
                try:
                    kwargs = get_stats_fn()
                    if asyncio.iscoroutine(kwargs):
                        kwargs = await kwargs
                    await self.periodic_update(**kwargs)
                except Exception as e:
                    logger.error(f"periodic_update stats fetch failed: {e}")

    # ------------------------------------------------------------------
    # System events
    # ------------------------------------------------------------------

    async def error(self, component: str, error_msg: str) -> None:
        msg = f"⚠️ <b>Error in {component}</b>\n<pre>{error_msg[:400]}</pre>"
        await self.send(msg)

    async def kill_switch(self, reason: str) -> None:
        msg = f"🚨 <b>KILL SWITCH ACTIVATED</b>\n{reason}"
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
            f"{status} <b>Daily Summary</b>\n"
            f"Daily PnL: <code>${daily_pnl:+.2f}</code>\n"
            f"Total PnL: <code>${total_pnl:+.2f}</code>\n"
            f"Win Rate: <code>{win_rate:.1%}</code> ({trades_count} trades)\n"
            f"Open Positions: <code>{open_positions}</code>"
        )
        await self.send(msg)

    async def circuit_breaker(self, consecutive_losses: int, pause_secs: int) -> None:
        msg = (
            f"⏸️ <b>Circuit Breaker</b>\n"
            f"{consecutive_losses} consecutive losses\n"
            f"Trading paused for {pause_secs // 60} minutes"
        )
        await self.send(msg)

    async def startup(self, paper_mode: bool, portfolio_size: float) -> None:
        mode = "📝 PAPER" if paper_mode else "💰 LIVE"
        msg = (
            f"🤖 <b>Bot Started</b> — {mode}\n"
            f"Portfolio: <code>${portfolio_size:.0f}</code>"
        )
        await self.send(msg)
