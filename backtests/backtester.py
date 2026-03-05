"""
Lag Arbitrage Backtester

Simulates the lag arbitrage strategy over historical Binance 1-minute kline data.

For each 15-minute window:
1. Model fair Polymarket YES prices (binary option formula)
2. Model lagged Polymarket prices (what the market actually shows, 60s behind)
3. Run strategy signal detection (same logic as live strategy)
4. Record trade: enter at lagged price, exit at resolution (0 or 1)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

WINDOW_MINS = 15       # 15-minute market
COOLDOWN_MINS = 5      # don't re-enter same window type within 5 minutes
LAG_SECS = 60          # simulated Polymarket lag behind Binance
SCALING = 10           # fair_value = 0.5 + |move| * scaling (matches live strategy)


@dataclass
class BacktestTrade:
    window_start: datetime
    minute_entered: int          # which minute bar we entered (1-14)
    direction: str               # "up" or "down"
    entry_price: float           # lagged Polymarket YES price at entry
    fair_price_at_entry: float   # what fair value was at entry
    edge_at_entry: float         # fair_price - entry_price
    confidence: float
    binance_move_pct: float      # 1-min Binance return that triggered signal
    resolution: float            # 1.0 (YES) or 0.0 (NO)
    pnl_per_dollar: float        # (resolution - entry_price) / entry_price
    position_size: float         # USDC notional
    pnl: float                   # absolute PnL

    @property
    def won(self) -> bool:
        return self.resolution == 1.0

    @property
    def correct_direction(self) -> bool:
        if self.direction == "up":
            return self.resolution == 1.0
        # resolution=1.0 always means "YES token paid" = we were right.
        # For UP: BTC went up. For DOWN: BTC went down. Both are wins.
        return self.resolution == 1.0


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    symbol: str = "BTC"
    days_tested: int = 0
    windows_tested: int = 0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # --- Computed metrics ---

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.correct_direction)
        return wins / len(self.trades)

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def avg_pnl(self) -> float:
        if not self.trades:
            return 0.0
        return self.total_pnl / len(self.trades)

    @property
    def avg_confidence(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.confidence for t in self.trades) / len(self.trades)

    @property
    def avg_edge(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.edge_at_entry for t in self.trades) / len(self.trades)

    @property
    def sharpe_ratio(self) -> float:
        if len(self.trades) < 2:
            return 0.0
        import statistics
        pnls = [t.pnl for t in self.trades]
        mean = statistics.mean(pnls)
        stdev = statistics.stdev(pnls)
        if stdev == 0:
            return 0.0
        return mean / stdev * (252 ** 0.5)  # annualised

    @property
    def max_drawdown(self) -> float:
        if not self.trades:
            return 0.0
        peak = 0.0
        drawdown = 0.0
        running = 0.0
        for t in self.trades:
            running += t.pnl
            if running > peak:
                peak = running
            dd = peak - running
            if dd > drawdown:
                drawdown = dd
        return drawdown

    @property
    def profit_factor(self) -> float:
        gross_win = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_win > 0 else 0.0
        return gross_win / gross_loss

    def pnl_by_day(self) -> dict[str, float]:
        daily: dict[str, float] = {}
        for t in self.trades:
            day = t.window_start.strftime("%Y-%m-%d")
            daily[day] = daily.get(day, 0.0) + t.pnl
        return daily

    def best_trade(self) -> Optional[BacktestTrade]:
        return max(self.trades, key=lambda t: t.pnl) if self.trades else None

    def worst_trade(self) -> Optional[BacktestTrade]:
        return min(self.trades, key=lambda t: t.pnl) if self.trades else None


class Backtester:
    """
    Runs the lag arbitrage strategy simulation over historical kline data.

    Strategy (mirrors live LagArbitrageStrategy):
    - For each minute bar in a 15-min window:
      - 1-min return = (close_now - close_prev) / close_prev
      - If |1-min return| > threshold AND edge > 0 AND confidence > min_confidence:
        → enter at lagged_price, exit at resolution
    """

    def __init__(
        self,
        threshold_pct: float = 0.003,
        min_confidence: float = 0.6,
        portfolio_size: float = 1000.0,
        max_position_pct: float = 0.02,
        daily_vol: float = 0.025,
        lag_secs: int = 60,
        cooldown_mins: int = 5,
    ):
        self.threshold_pct = threshold_pct
        self.min_confidence = min_confidence
        self.max_position_size = portfolio_size * max_position_pct
        self.daily_vol = daily_vol
        self.lag_secs = lag_secs
        self.cooldown_mins = cooldown_mins

    def run(
        self,
        df_1m: pd.DataFrame,
        symbol: str = "BTC",
    ) -> BacktestResult:
        """
        Run the full backtest.

        Args:
            df_1m: DataFrame with columns [open_time, open, high, low, close, volume]
                   1-minute bars, sorted ascending, open_time in UTC.
            symbol: "BTC", "ETH", or "SOL"

        Returns:
            BacktestResult with all trades and metrics.
        """
        from backtests.market_model import BinaryMarketModel

        if df_1m.empty:
            logger.error("Empty DataFrame — cannot run backtest")
            return BacktestResult(symbol=symbol)

        model = BinaryMarketModel(
            window_secs=WINDOW_MINS * 60,
            daily_vol=self.daily_vol,
            lag_secs=self.lag_secs,
        )

        result = BacktestResult(symbol=symbol)
        result.start_date = df_1m["open_time"].iloc[0].to_pydatetime()
        result.end_date = df_1m["open_time"].iloc[-1].to_pydatetime()

        closes = df_1m["close"].values
        times = df_1m["open_time"].values
        n = len(closes)

        last_trade_bar = -self.cooldown_mins  # track cooldown
        windows_tested = 0

        # Slide a 15-min window over the data
        for w_start in range(0, n - WINDOW_MINS, WINDOW_MINS):
            w_end = w_start + WINDOW_MINS
            window_closes = closes[w_start:w_end].tolist()
            window_start_dt = pd.Timestamp(times[w_start]).to_pydatetime()

            if len(window_closes) < WINDOW_MINS:
                continue

            windows_tested += 1
            bars = model.simulate_window(window_closes)

            traded_this_window = False

            for bar in bars[1:]:  # skip minute 0 (no prev bar to compute return)
                if traded_this_window:
                    break

                minute = bar["minute"]
                global_bar = w_start + minute

                # Cooldown check
                if global_bar - last_trade_bar < self.cooldown_mins:
                    continue

                # 1-min Binance return (proxy for 60-second momentum)
                if minute == 0:
                    continue
                prev_close = window_closes[minute - 1]
                curr_close = window_closes[minute]
                if prev_close == 0:
                    continue
                move_1m = (curr_close - prev_close) / prev_close

                if abs(move_1m) < self.threshold_pct:
                    continue

                direction = "up" if move_1m > 0 else "down"

                # UP token prices from model; DOWN token = 1 - UP token
                if direction == "up":
                    entry_lagged = bar["lagged_price"]
                    entry_fair = bar["fair_price"]
                else:
                    entry_lagged = 1.0 - bar["lagged_price"]
                    entry_fair = 1.0 - bar["fair_price"]

                # Mirror live strategy edge/confidence logic
                # fair_value_strat = expected value of the token we're buying
                fair_value_strat = 0.5 + abs(move_1m) * SCALING
                fair_value_strat = min(fair_value_strat, 0.95)
                edge = fair_value_strat - entry_lagged

                # Only trade near-neutral markets (0.40-0.60).
                # Lag arbitrage captures the price update lag right after window
                # open — the market should be near 50/50 when we enter.
                # Entries outside this range mean the market already priced in
                # the move before we could act.
                if edge <= 0 or not (0.40 <= entry_lagged <= 0.60):
                    continue

                move_conf = min(abs(move_1m) / (self.threshold_pct * 3), 1.0)
                edge_conf = min(edge / 0.15, 1.0)
                confidence = 0.5 * move_conf + 0.5 * edge_conf

                if confidence < self.min_confidence:
                    continue

                # Determine resolution: did price go in the signalled direction?
                final_close = window_closes[-1]
                open_price = window_closes[0]
                final_return = (final_close - open_price) / open_price

                if direction == "up":
                    resolution = 1.0 if final_return > 0 else 0.0
                else:
                    resolution = 1.0 if final_return < 0 else 0.0

                # PnL: we bought YES at entry_lagged, exits at resolution
                pnl_per_dollar = (resolution - entry_lagged) / entry_lagged
                size = self.max_position_size * min(confidence, 1.0)
                pnl = size * pnl_per_dollar

                trade = BacktestTrade(
                    window_start=window_start_dt,
                    minute_entered=minute,
                    direction=direction,
                    entry_price=entry_lagged,
                    fair_price_at_entry=entry_fair,
                    edge_at_entry=edge,
                    confidence=confidence,
                    binance_move_pct=move_1m,
                    resolution=resolution,
                    pnl_per_dollar=pnl_per_dollar,
                    position_size=size,
                    pnl=pnl,
                )
                result.trades.append(trade)
                last_trade_bar = global_bar
                traded_this_window = True

        result.windows_tested = windows_tested
        unique_days = len(set(
            pd.Timestamp(t).date() for t in df_1m["open_time"].values
        ))
        result.days_tested = unique_days

        logger.info(
            f"Backtest complete: {result.num_trades} trades over "
            f"{result.days_tested} days ({result.windows_tested} windows)"
        )
        return result
