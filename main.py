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
from src.execution.shadow_logger import ShadowLogger


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

        # Shadow mode — tracks rejected signals and their hypothetical outcomes
        self.shadow_logger = ShadowLogger(
            csv_path=os.path.join(settings.TRADES_DIR, "shadow_trades.csv")
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
            binance_price=price,
        )
        if signal is None:
            # Capture shadow signal if strategy rejected a meaningful candidate
            if self.strategy.last_shadow:
                self.shadow_logger.log_rejected_signal(self.strategy.last_shadow)
            return

        # Pre-trade sanity check: refuse entries outside the genuine uncertainty zone.
        # Prices near 0 or 1 mean the market is nearly resolved — wrong market or
        # expired window. This is a final safety net in case market discovery
        # slips through with a stale token.
        if not (0.35 <= signal.poly_price <= 0.65):
            logger.warning(
                f"Trade rejected — entry price {signal.poly_price:.4f} outside "
                f"safe range [0.35, 0.65] for {signal.symbol} {signal.direction.upper()}. "
                f"Market may be nearly resolved. Skipping."
            )
            self.shadow_logger.log_rejected_signal({
                "symbol": signal.symbol,
                "token_id": signal.token_id,
                "direction": signal.direction,
                "filter_reason": "main_price_range",
                "binance_move_pct": signal.binance_move_pct,
                "confidence": signal.confidence,
                "fair_value": None,
                "edge": None,
                "poly_price": signal.poly_price,
                "timestamp": signal.timestamp,
            })
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
            self.shadow_logger.log_rejected_signal({
                "symbol": signal.symbol,
                "token_id": signal.token_id,
                "direction": signal.direction,
                "filter_reason": f"risk:{reason}",
                "binance_move_pct": signal.binance_move_pct,
                "confidence": signal.confidence,
                "fair_value": None,
                "edge": None,
                "poly_price": signal.poly_price,
                "timestamp": signal.timestamp,
            })
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
        self.shadow_logger.update_price(token_id, mid)

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
        """
        Discover current 15-min BTC/ETH/SOL market token IDs via Gamma API slug lookup.

        Slugs follow the pattern  {coin}-updown-15m-{unix_timestamp}  where the
        timestamp is the UTC start of the current 15-minute window.  We try the
        current window, the next window, and the previous window so we always
        land on one that is still acceptingOrders.
        """
        from datetime import datetime, timezone

        COIN_SLUGS = {
            "BTC": "btc-updown-15m",
            "ETH": "eth-updown-15m",
            "SOL": "sol-updown-15m",
        }

        now = datetime.now(timezone.utc)
        minute = (now.minute // 15) * 15
        current_window = now.replace(minute=minute, second=0, microsecond=0)
        current_ts = int(current_window.timestamp())
        candidates = [current_ts, current_ts + 900, current_ts - 900]

        token_ids: dict[str, dict[str, str]] = {}

        try:
            import aiohttp
            headers = {"User-Agent": "ProjectDA/1.0", "Accept": "application/json"}
            async with aiohttp.ClientSession(headers=headers) as session:
                for sym in settings.SYMBOLS:
                    prefix = COIN_SLUGS.get(sym)
                    if not prefix:
                        continue
                    for ts in candidates:
                        slug = f"{prefix}-{ts}"
                        url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"
                        try:
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                                if r.status != 200:
                                    continue
                                m = await r.json(content_type=None)
                            if not m or not m.get("acceptingOrders"):
                                continue
                            # Map outcomes → token IDs  (outcomes[0]="Up", outcomes[1]="Down")
                            raw_ids = m.get("clobTokenIds") or []
                            if isinstance(raw_ids, str):
                                import json as _json
                                raw_ids = _json.loads(raw_ids)
                            raw_outcomes = m.get("outcomes") or ["Up", "Down"]
                            if isinstance(raw_outcomes, str):
                                import json as _json
                                raw_outcomes = _json.loads(raw_outcomes)
                            sym_tokens: dict[str, str] = {}
                            for i, outcome in enumerate(raw_outcomes):
                                if i < len(raw_ids):
                                    sym_tokens[str(outcome).lower()] = raw_ids[i]
                            if "up" in sym_tokens and "down" in sym_tokens:
                                # --- Price filter: only trade near-open markets ---
                                # Markets near expiry have prices like 0.001/0.999.
                                # Only accept a market if the UP price is 0.40–0.60
                                # (genuine uncertainty zone near window open).
                                raw_prices = m.get("outcomePrices") or '["0.5","0.5"]'
                                if isinstance(raw_prices, str):
                                    import json as _json
                                    raw_prices = _json.loads(raw_prices)
                                up_idx = next(
                                    (i for i, o in enumerate(raw_outcomes)
                                     if str(o).lower() == "up"), 0
                                )
                                up_price = float(raw_prices[up_idx]) if up_idx < len(raw_prices) else 0.5
                                if not (0.40 <= up_price <= 0.60):
                                    logger.info(
                                        f"Skipping {sym} market (UP price={up_price:.3f} "
                                        f"outside [0.40, 0.60] — market nearly resolved): "
                                        f"{m.get('question','')[:50]}"
                                    )
                                    continue  # try next candidate timestamp

                                token_ids[sym] = sym_tokens

                                # Seed polymarket prices so strategy has real numbers
                                # before the first WS book event arrives
                                for i, outcome in enumerate(raw_outcomes):
                                    if i < len(raw_ids) and i < len(raw_prices):
                                        tid = raw_ids[i]
                                        p = float(raw_prices[i])
                                        self.polymarket.prices[tid] = p
                                        logger.info(
                                            f"Seeded {sym} {str(outcome).upper()} price={p:.4f} "
                                            f"from Gamma (token {tid[:12]}…)"
                                        )

                                logger.info(
                                    f"Discovered {sym} market: {m.get('question','')[:60]} "
                                    f"(up={raw_ids[0][:12]}… down={raw_ids[1][:12]}…)"
                                )
                                break  # found a valid near-0.50 market for this symbol
                        except Exception as e:
                            logger.debug(f"Slug lookup {slug}: {e}")
                            continue
        except Exception as e:
            logger.warning(f"Market discovery error: {e}")

        if not token_ids:
            logger.warning("Market discovery: no accepting markets found for any symbol")
        return token_ids

    # ------------------------------------------------------------------
    # Periodic market refresh (15-min markets expire and rotate)
    # ------------------------------------------------------------------

    async def _refresh_markets_loop(self) -> None:
        """Re-discover token IDs every 10 minutes so we track the live window."""
        while not self._stop_event.is_set():
            await asyncio.sleep(600)  # 10 minutes
            logger.info("Refreshing 15-min market token IDs...")
            token_ids = await self._discover_markets()
            if token_ids:
                self.strategy.update_token_ids(token_ids)
                all_ids = [tid for market in token_ids.values() for tid in market.values()]
                self.polymarket.token_ids = all_ids
                await self.polymarket.resubscribe()
                logger.info(f"Market refresh complete — tracking {len(all_ids)} tokens")
            else:
                logger.warning("Market refresh found no accepting markets — retrying next cycle")

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
            asyncio.create_task(self._refresh_markets_loop(), name="market_refresh"),
        ]

        logger.info("All tasks started — bot is running")
        await self._stop_event.wait()
        await self.shutdown()

    def _request_shutdown(self) -> None:
        logger.info("Shutdown requested")
        self._stop_event.set()

    async def shutdown(self) -> None:
        logger.info("Shutting down...")
        self.shadow_logger.expire_all()
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
