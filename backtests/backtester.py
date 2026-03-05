"""
Lag Arbitrage Backtester

Simulates the lag arbitrage strategy over historical Binance 1-minute kline data
with configurable execution realism parameters.

Execution realism parameters
-----------------------------
execution_delay_secs : float
    Time (seconds) between signal detection and order fill. Models network
    latency + order routing. During this window, Polymarket starts moving.

market_impact_pct : float  [0.0 – 1.0]
    Fraction of the edge consumed by other bots front-running the same signal.
    actual_fill_price = entry_lagged + market_impact_pct * edge
    0.0 = no impact (we're first), 1.0 = edge fully gone before we fill.

fill_probability : float  [0.0 – 1.0]
    Probability our order actually gets filled in thin market conditions.
    Models partial orderbook depth and missed fills.

scenario_name : str
    Label shown in the report ("optimistic", "realistic", "pessimistic").
"""
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

WINDOW_MINS = 15       # 15-minute market
COOLDOWN_MINS = 5      # don't re-enter same window type within 5 minutes
LAG_SECS = 60          # simulated Polymarket lag behind Binance
SCALING = 10           # fair_value = 0.5 + |move| * scaling (matches live strategy)

# --- Pre-defined scenario configs ---

SCENARIO_OPTIMISTIC = dict(
    scenario_name="optimistic",
    execution_delay_secs=0.0,
    market_impact_pct=0.0,
    fill_probability=1.0,
)
SCENARIO_REALISTIC = dict(
    scenario_name="realistic",
    execution_delay_secs=1.5,
    market_impact_pct=0.30,
    fill_probability=0.65,
)
SCENARIO_PESSIMISTIC = dict(
    scenario_name="pessimistic",
    execution_delay_secs=3.0,
    market_impact_pct=0.60,
    fill_probability=0.40,
)


@dataclass
class BacktestTrade:
    window_start: datetime
    minute_entered: int          # which minute bar we entered (1-14)
    direction: str               # "up" or "down"
    entry_price: float           # lagged Polymarket YES price (pre-impact)
    actual_fill_price: float     # price actually paid after market impact
    fair_price_at_entry: float   # what binary option fair value was at entry
    edge_at_entry: float         # fair_value_strat - entry_price (pre-impact)
    edge_after_impact: float     # edge remaining after market_impact_pct applied
    confidence: float
    binance_move_pct: float      # 1-min Binance return that triggered signal
    resolution: float            # 1.0 (YES paid) or 0.0 (NO)
    pnl_per_dollar: float        # (resolution - actual_fill_price) / actual_fill_price
    position_size: float         # USDC notional
    pnl: float                   # gross PnL (before fees)
    fees_paid: float             # entry fee + exit fee in USDC
    pnl_net: float               # net PnL after fees

    @property
    def won(self) -> bool:
        return self.resolution == 1.0

    @property
    def correct_direction(self) -> bool:
        # resolution=1.0 always means "YES token paid" = we were right.
        return self.resolution == 1.0


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    symbol: str = "BTC"
    days_tested: int = 0
    windows_tested: int = 0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # Scenario metadata
    scenario_name: str = "optimistic"
    execution_delay_secs: float = 0.0
    market_impact_pct: float = 0.0
    fill_probability: float = 1.0
    # Tracking
    attempted_signals: int = 0   # signals that passed edge/confidence but failed fill check

    # --- Computed metrics ---

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def fill_rate(self) -> float:
        total = self.num_trades + self.attempted_signals
        return self.num_trades / total if total > 0 else 0.0

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
    def total_fees_paid(self) -> float:
        return sum(t.fees_paid for t in self.trades)

    @property
    def total_pnl_net(self) -> float:
        return sum(t.pnl_net for t in self.trades)

    @property
    def avg_pnl(self) -> float:
        if not self.trades:
            return 0.0
        return self.total_pnl / len(self.trades)

    @property
    def avg_pnl_net(self) -> float:
        if not self.trades:
            return 0.0
        return self.total_pnl_net / len(self.trades)

    @property
    def avg_edge_pre_impact(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.edge_at_entry for t in self.trades) / len(self.trades)

    @property
    def avg_edge_post_impact(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.edge_after_impact for t in self.trades) / len(self.trades)

    @property
    def avg_confidence(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.confidence for t in self.trades) / len(self.trades)

    def _sharpe(self, pnls: list) -> float:
        if len(pnls) < 2:
            return 0.0
        import statistics
        mean = statistics.mean(pnls)
        stdev = statistics.stdev(pnls)
        return 0.0 if stdev == 0 else mean / stdev * (252 ** 0.5)

    def _max_drawdown(self, pnls: list) -> float:
        peak = drawdown = running = 0.0
        for p in pnls:
            running += p
            peak = max(peak, running)
            drawdown = max(drawdown, peak - running)
        return drawdown

    def _profit_factor(self, pnls: list) -> float:
        wins = sum(p for p in pnls if p > 0)
        losses = abs(sum(p for p in pnls if p < 0))
        if losses == 0:
            return float("inf") if wins > 0 else 0.0
        return wins / losses

    @property
    def sharpe_ratio(self) -> float:
        return self._sharpe([t.pnl for t in self.trades])

    @property
    def sharpe_ratio_net(self) -> float:
        return self._sharpe([t.pnl_net for t in self.trades])

    @property
    def max_drawdown(self) -> float:
        return self._max_drawdown([t.pnl for t in self.trades])

    @property
    def max_drawdown_net(self) -> float:
        return self._max_drawdown([t.pnl_net for t in self.trades])

    @property
    def profit_factor(self) -> float:
        return self._profit_factor([t.pnl for t in self.trades])

    @property
    def profit_factor_net(self) -> float:
        return self._profit_factor([t.pnl_net for t in self.trades])

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

    Three execution realism scenarios supported (see module-level constants):
        SCENARIO_OPTIMISTIC  — no impact, always fills (upper bound)
        SCENARIO_REALISTIC   — 1.5s delay, 30% impact, 65% fill rate
        SCENARIO_PESSIMISTIC — 3.0s delay, 60% impact, 40% fill rate
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
        # Execution realism
        scenario_name: str = "optimistic",
        execution_delay_secs: float = 0.0,
        market_impact_pct: float = 0.0,
        fill_probability: float = 1.0,
        random_seed: int = 42,
        # Fees
        fee_entry_pct: float = 0.02,   # 2% on USDC spent at entry
        fee_exit_pct: float = 0.02,    # 2% on payout received at exit
    ):
        self.threshold_pct = threshold_pct
        self.min_confidence = min_confidence
        self.max_position_size = portfolio_size * max_position_pct
        self.daily_vol = daily_vol
        self.lag_secs = lag_secs
        self.cooldown_mins = cooldown_mins
        self.scenario_name = scenario_name
        self.execution_delay_secs = execution_delay_secs
        self.market_impact_pct = market_impact_pct
        self.fill_probability = fill_probability
        self.random_seed = random_seed
        self.fee_entry_pct = fee_entry_pct
        self.fee_exit_pct = fee_exit_pct

    def run(
        self,
        df_1m: pd.DataFrame,
        symbol: str = "BTC",
    ) -> BacktestResult:
        """
        Run the full backtest with configured execution realism parameters.

        Args:
            df_1m: DataFrame [open_time, open, high, low, close, volume], 1-min UTC bars.
            symbol: "BTC", "ETH", or "SOL"

        Returns:
            BacktestResult
        """
        from backtests.market_model import BinaryMarketModel

        rng = random.Random(self.random_seed)  # deterministic per scenario

        if df_1m.empty:
            logger.error("Empty DataFrame — cannot run backtest")
            return BacktestResult(symbol=symbol, scenario_name=self.scenario_name)

        model = BinaryMarketModel(
            window_secs=WINDOW_MINS * 60,
            daily_vol=self.daily_vol,
            lag_secs=self.lag_secs,
        )

        result = BacktestResult(
            symbol=symbol,
            scenario_name=self.scenario_name,
            execution_delay_secs=self.execution_delay_secs,
            market_impact_pct=self.market_impact_pct,
            fill_probability=self.fill_probability,
        )
        result.start_date = df_1m["open_time"].iloc[0].to_pydatetime()
        result.end_date = df_1m["open_time"].iloc[-1].to_pydatetime()

        closes = df_1m["close"].values
        times = df_1m["open_time"].values
        n = len(closes)

        last_trade_bar = -self.cooldown_mins
        windows_tested = 0

        # Remaining window time after execution delay (in seconds)
        exec_delay = self.execution_delay_secs

        for w_start in range(0, n - WINDOW_MINS, WINDOW_MINS):
            w_end = w_start + WINDOW_MINS
            window_closes = closes[w_start:w_end].tolist()
            window_start_dt = pd.Timestamp(times[w_start]).to_pydatetime()

            if len(window_closes) < WINDOW_MINS:
                continue

            windows_tested += 1
            bars = model.simulate_window(window_closes)

            traded_this_window = False

            for bar in bars[1:]:
                if traded_this_window:
                    break

                minute = bar["minute"]
                global_bar = w_start + minute

                if global_bar - last_trade_bar < self.cooldown_mins:
                    continue

                if minute == 0:
                    continue

                prev_close = window_closes[minute - 1]
                curr_close = window_closes[minute]
                if prev_close == 0:
                    continue
                move_1m = (curr_close - prev_close) / prev_close

                if abs(move_1m) < self.threshold_pct:
                    continue

                # Check enough window time remains after execution delay
                elapsed_secs = minute * 60
                remaining_after_fill = (WINDOW_MINS * 60) - elapsed_secs - exec_delay
                if remaining_after_fill < 60:
                    # Less than 1 minute remaining after fill — skip
                    continue

                direction = "up" if move_1m > 0 else "down"

                if direction == "up":
                    entry_lagged = bar["lagged_price"]
                    entry_fair = bar["fair_price"]
                else:
                    entry_lagged = 1.0 - bar["lagged_price"]
                    entry_fair = 1.0 - bar["fair_price"]

                fair_value_strat = 0.5 + abs(move_1m) * SCALING
                fair_value_strat = min(fair_value_strat, 0.95)
                edge = fair_value_strat - entry_lagged

                # Only trade near-neutral markets — real lag opportunity zone
                if edge <= 0 or not (0.40 <= entry_lagged <= 0.60):
                    continue

                move_conf = min(abs(move_1m) / (self.threshold_pct * 3), 1.0)
                edge_conf = min(edge / 0.15, 1.0)
                confidence = 0.5 * move_conf + 0.5 * edge_conf

                if confidence < self.min_confidence:
                    continue

                # --- Execution realism ---

                # 1. Fill probability check — models thin orderbook / missed fills
                if rng.random() > self.fill_probability:
                    result.attempted_signals += 1
                    last_trade_bar = global_bar  # cooldown still burns
                    traded_this_window = True
                    continue

                # 2. Market impact — price moves toward fair value during execution delay
                #    actual_fill = entry_lagged + impact_pct * edge
                actual_fill = entry_lagged + self.market_impact_pct * edge
                edge_after_impact = fair_value_strat - actual_fill

                if edge_after_impact <= 0:
                    # Edge fully consumed — skip (would be a losing fill)
                    result.attempted_signals += 1
                    last_trade_bar = global_bar
                    traded_this_window = True
                    continue

                # Guard against degenerate fill prices
                if actual_fill <= 0.001 or actual_fill >= 0.999:
                    continue

                # --- Resolution ---
                final_close = window_closes[-1]
                open_price = window_closes[0]
                final_return = (final_close - open_price) / open_price

                if direction == "up":
                    resolution = 1.0 if final_return > 0 else 0.0
                else:
                    resolution = 1.0 if final_return < 0 else 0.0

                pnl_per_dollar = (resolution - actual_fill) / actual_fill
                size = self.max_position_size * min(confidence, 1.0)
                pnl = size * pnl_per_dollar  # gross (no fees)

                # --- Fee calculation ---
                # Entry: 2% of size → fewer tokens received
                # Exit:  2% of payout → only applies when resolution > 0
                capital_in = size * (1.0 - self.fee_entry_pct)
                tokens = capital_in / actual_fill
                gross_payout = tokens * resolution
                net_payout = (
                    gross_payout * (1.0 - self.fee_exit_pct)
                    if resolution > 0 else 0.0
                )
                fee_entry = size * self.fee_entry_pct
                fee_exit = gross_payout * self.fee_exit_pct if resolution > 0 else 0.0
                fees_paid = fee_entry + fee_exit
                pnl_net = net_payout - size

                trade = BacktestTrade(
                    window_start=window_start_dt,
                    minute_entered=minute,
                    direction=direction,
                    entry_price=entry_lagged,
                    actual_fill_price=actual_fill,
                    fair_price_at_entry=entry_fair,
                    edge_at_entry=edge,
                    edge_after_impact=edge_after_impact,
                    confidence=confidence,
                    binance_move_pct=move_1m,
                    resolution=resolution,
                    pnl_per_dollar=pnl_per_dollar,
                    position_size=size,
                    pnl=pnl,
                    fees_paid=fees_paid,
                    pnl_net=pnl_net,
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
            f"[{self.scenario_name.upper()}] {result.num_trades} filled trades "
            f"({result.attempted_signals} missed fills) over "
            f"{result.days_tested} days | "
            f"PnL gross=${result.total_pnl:+.2f} "
            f"net=${result.total_pnl_net:+.2f} "
            f"fees=${result.total_fees_paid:.2f} "
            f"| Win={result.win_rate:.1%}"
        )
        return result
