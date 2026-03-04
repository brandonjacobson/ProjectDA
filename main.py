"""
ProjectDA — Polymarket Lag Arbitrage Bot
Entry point: orchestrates all modules, graceful shutdown, startup checks.

Usage:
    python main.py            # paper mode (default)
    python main.py --live     # LIVE TRADING (real money — use with caution)
    python main.py --help
"""
import argparse
import asyncio
import logging
import os
import signal
import sys
import time

# ---------------------------------------------------------------------------
# Logging setup (before other imports so all loggers are configured)
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join("logs", "bot.log"), mode="a"),
    ],
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from config import settings
from src.data.binance_feed import BinanceFeed
from src.data.polymarket_feed import PolymarketFeed
from src.strategies.lag_arbitrage import LagArbitrageStrategy
from src.execution.order_manager import OrderManager
from src.risk.risk_engine import RiskEngine
from src.monitoring.alerts import AlertManager
from src.monitoring.dashboard import Dashboard


class Bot:
    """Top-level orchestrator — wires together all components."""

    def __init__(self, live: bool = False):
        self.paper_mode = not live
        logger.info(f"Initialising in {'LIVE' if live else 'PAPER'} mode")

        # Core components
        self.risk = RiskEngine(
            portfolio_size=settings.PORTFOLIO_SIZE,
            max_position_pct=settings.MAX_POSITION_PCT,
            daily_loss_cap_pct=settings.DAILY_LOSS_CAP_PCT,
            max_concurrent=settings.MAX_CONCURRENT_POSITIONS,
            circuit_breaker_losses=settings.CIRCUIT_BREAKER_LOSSES,
            circuit_breaker_pause_secs=settings.CIRCUIT_BREAKER_PAUSE_SECS,
        )
        self.order_manager = OrderManager(
            paper_mode=self.paper_mode,
            trades_dir=settings.TRADES_DIR,
            portfolio_size=settings.PORTFOLIO_SIZE,
        )
        self.strategy = LagArbitrageStrategy(
            threshold_pct=settings.LAG_THRESHOLD_PCT,
            lookback_secs=settings.LAG_LOOKBACK_SECS,
            min_confidence=settings.MIN_CONFIDENCE,
        )
        self.alerts = AlertManager(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=settings.TELEGRAM_CHAT_ID,
            enabled=settings.ALERTS_ENABLED,
        )
        self.dashboard = Dashboard(
            order_manager=self.order_manager,
            risk_engine=self.risk,
            refresh_secs=settings.DASHBOARD_REFRESH_SECS,
            paper_mode=self.paper_mode,
        )

        # Feeds — token_ids will be populated after market discovery
        self.binance = BinanceFeed(
            symbols=settings.SYMBOLS,
            on_price=self._on_binance_price,
        )
        self.polymarket = PolymarketFeed(
            token_ids=[],  # filled in startup_checks
            on_book_update=self._on_poly_book,
        )

        # Wire kill-switch → alert
        self.risk.on_kill_switch(self._on_kill_switch)

        # Shutdown event
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._daily_summary_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    async def _on_binance_price(self, symbol: str, price: float, ts: float) -> None:
        """Called on every Binance trade tick — evaluate strategy."""
        if self.risk.kill_switch_active or self.risk.is_circuit_breaker_active():
            return

        move_pct = self.binance.get_price_change_pct(symbol, self.strategy.lookback_secs)
        signal = self.strategy.evaluate(
            symbol=symbol,
            binance_move_pct=move_pct,
            poly_prices=self.polymarket.prices,
        )
        if signal is None:
            return

        # Risk check
        size = self.risk.calculate_position_size(signal.confidence)
        allowed, reason = self.risk.check_trade(
            open_position_count=len(self.order_manager.open_positions),
            daily_pnl=self.order_manager.daily_pnl,
            size=size,
        )
        if not allowed:
            logger.info(f"Trade blocked by risk: {reason}")
            return

        # Place order
        record = await self.order_manager.place_order(
            token_id=signal.token_id,
            symbol=signal.symbol,
            direction=signal.direction,
            size=size,
            price=signal.poly_price,
            confidence=signal.confidence,
        )
        if record:
            await self.alerts.trade_opened(
                signal.symbol, signal.direction, size, signal.poly_price, signal.confidence
            )

    async def _on_poly_book(self, token_id: str, bids, asks, mid: float) -> None:
        """Update open position prices from Polymarket order book."""
        self.order_manager.update_price(token_id, mid)

        # Simple exit logic: close if market price moves against us heavily
        pos = self.order_manager.positions.get(token_id)
        if pos and not pos.closed:
            # Exit at ~90% resolved or ~20% stop loss
            if mid >= 0.85 or pos.pnl_pct <= -0.20:
                reason = "take_profit" if mid >= 0.85 else "stop_loss"
                record = await self.order_manager.close_position(token_id, mid, reason)
                if record:
                    self.risk.record_trade_result(pos.pnl)
                    await self.alerts.trade_closed(
                        pos.symbol, pos.direction, pos.pnl, pos.pnl_pct, reason
                    )

    async def _on_kill_switch(self, reason: str) -> None:
        await self.alerts.kill_switch(reason)
        logger.critical(f"Kill switch: {reason}. Closing all positions...")
        for token_id in list(self.order_manager.positions.keys()):
            price = self.polymarket.get_price(token_id) or 0.5
            await self.order_manager.close_position(token_id, price, "kill_switch")

    # ------------------------------------------------------------------
    # Startup checks
    # ------------------------------------------------------------------

    async def startup_checks(self) -> bool:
        """Check connectivity and resolve market token IDs."""
        logger.info("Running startup checks...")
        os.makedirs(settings.LOG_DIR, exist_ok=True)
        os.makedirs(settings.TRADES_DIR, exist_ok=True)

        # Resolve 15-min market token IDs via Gamma API
        token_ids = await self._discover_markets()
        if token_ids:
            self.strategy.update_token_ids(token_ids)
            all_ids = [tid for market in token_ids.values() for tid in market.values()]
            self.polymarket.token_ids = all_ids
            logger.info(f"Resolved {len(all_ids)} market token IDs")
        else:
            logger.warning("Market discovery failed — using placeholder token IDs")

        logger.info("Startup checks complete")
        return True

    async def _discover_markets(self) -> dict:
        """Try to discover current 15-min BTC/ETH/SOL market token IDs via Gamma API."""
        try:
            import aiohttp
            gamma_url = "https://gamma-api.polymarket.com/markets"
            params = {"active": "true", "limit": 500}
            async with aiohttp.ClientSession() as session:
                async with session.get(gamma_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        return {}
                    markets = await r.json()

            token_ids: dict[str, dict[str, str]] = {}
            for m in markets:
                question = (m.get("question") or "").lower()
                for sym in settings.SYMBOLS:
                    if sym.lower() in question and "15" in question:
                        direction = None
                        if "higher" in question or "up" in question or "above" in question:
                            direction = "up"
                        elif "lower" in question or "down" in question or "below" in question:
                            direction = "down"
                        if direction:
                            clob_token_ids = m.get("clobTokenIds") or []
                            if clob_token_ids:
                                token_ids.setdefault(sym, {})[direction] = clob_token_ids[0]
            return token_ids
        except Exception as e:
            logger.warning(f"Market discovery error: {e}")
            return {}

    # ------------------------------------------------------------------
    # Daily summary scheduler
    # ------------------------------------------------------------------

    async def _schedule_daily_summary(self) -> None:
        """Send daily summary at 23:55 UTC."""
        while not self._stop_event.is_set():
            now = time.gmtime()
            if now.tm_hour == 23 and now.tm_min == 55:
                await self.alerts.daily_summary(
                    total_pnl=self.order_manager.total_pnl,
                    daily_pnl=self.order_manager.daily_pnl,
                    win_rate=self.order_manager.win_rate,
                    trades_count=len(self.order_manager.closed_positions),
                    open_positions=len(self.order_manager.open_positions),
                )
                await asyncio.sleep(120)  # avoid double-send within the same minute
            await asyncio.sleep(60)

    # ------------------------------------------------------------------
    # Run / shutdown
    # ------------------------------------------------------------------

    async def run(self) -> None:
        if not await self.startup_checks():
            logger.error("Startup checks failed — aborting")
            return

        await self.alerts.startup(self.paper_mode, settings.PORTFOLIO_SIZE)

        # Register OS signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_shutdown)

        # Launch background tasks
        self._tasks = [
            asyncio.create_task(self.binance.run(), name="binance_feed"),
            asyncio.create_task(self.polymarket.run(), name="poly_feed"),
            asyncio.create_task(self.dashboard.run(), name="dashboard"),
            asyncio.create_task(self._schedule_daily_summary(), name="daily_summary"),
        ]

        logger.info("All tasks started — bot is running")
        await self._stop_event.wait()
        await self.shutdown()

    def _request_shutdown(self) -> None:
        logger.info("Shutdown requested")
        self._stop_event.set()

    async def shutdown(self) -> None:
        logger.info("Shutting down...")
        await self.binance.stop()
        await self.polymarket.stop()
        self.dashboard.stop()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="ProjectDA — Polymarket Lag Arbitrage Bot")
    parser.add_argument("--live", action="store_true", help="Enable live trading (real money)")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.live:
        print("\n⚠️  LIVE MODE REQUESTED — real money will be traded. Ctrl-C to abort.\n")
        import time as _time
        _time.sleep(3)

    bot = Bot(live=args.live)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
