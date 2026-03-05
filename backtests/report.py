"""
Backtest report generator — writes backtests/results.md
"""
import os
from datetime import datetime, timezone

from backtests.backtester import BacktestResult


def generate_report(result: BacktestResult, output_path: str = "backtests/results.md") -> str:
    """Generate a full performance report and write to output_path. Returns the markdown string."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Lag Arbitrage Backtest — Performance Report",
        f"",
        f"**Generated:** {now}  ",
        f"**Symbol:** {result.symbol}  ",
        f"**Period:** {_fmt_date(result.start_date)} → {_fmt_date(result.end_date)}  ",
        f"**Days tested:** {result.days_tested}  ",
        f"**15-min windows:** {result.windows_tested}  ",
        "",
        "---",
        "",
        "## Strategy Parameters",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        "| Binance move threshold | 0.3% per minute |",
        "| Lookback window | 60 seconds (1 bar) |",
        "| Simulated Poly lag | 60 seconds |",
        "| Min confidence | 0.60 |",
        "| Scaling factor | 10× |",
        "| Portfolio size | $1,000 |",
        "| Max position | 2% ($20) |",
        "| Market window | 15 minutes |",
        "",
        "---",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total trades | {result.num_trades} |",
        f"| Win rate (correct direction) | {result.win_rate:.1%} |",
        f"| Total PnL | ${result.total_pnl:+.2f} |",
        f"| Avg PnL per trade | ${result.avg_pnl:+.4f} |",
        f"| Avg edge at entry | {result.avg_edge:.3f} |",
        f"| Avg confidence | {result.avg_confidence:.2f} |",
        f"| Profit factor | {result.profit_factor:.2f} |",
        f"| Sharpe ratio (ann.) | {result.sharpe_ratio:.2f} |",
        f"| Max drawdown | ${result.max_drawdown:.2f} |",
    ]

    best = result.best_trade()
    worst = result.worst_trade()
    if best:
        lines.append(f"| Best trade | ${best.pnl:+.2f} ({_fmt_date(best.window_start)}) |")
    if worst:
        lines.append(f"| Worst trade | ${worst.pnl:+.2f} ({_fmt_date(worst.window_start)}) |")

    lines += [
        "",
        "---",
        "",
        "## Daily P&L",
        "",
        "| Date | PnL | Cumulative |",
        "|------|-----|-----------|",
    ]

    daily = result.pnl_by_day()
    cumulative = 0.0
    for day in sorted(daily.keys()):
        pnl = daily[day]
        cumulative += pnl
        emoji = "🟢" if pnl >= 0 else "🔴"
        lines.append(f"| {day} | {emoji} ${pnl:+.2f} | ${cumulative:+.2f} |")

    lines += [
        "",
        "---",
        "",
        "## Trade Log",
        "",
        "| # | Date | Min | Dir | Entry | Fair | Edge | Conf | Binance% | Resolution | PnL |",
        "|---|------|-----|-----|-------|------|------|------|----------|------------|-----|",
    ]

    for i, t in enumerate(result.trades, 1):
        lines.append(
            f"| {i} | {_fmt_date(t.window_start)} | {t.minute_entered} "
            f"| {t.direction.upper()} | {t.entry_price:.3f} | {t.fair_price_at_entry:.3f} "
            f"| {t.edge_at_entry:.3f} | {t.confidence:.2f} | {t.binance_move_pct:+.3%} "
            f"| {'✅' if t.correct_direction else '❌'} {t.resolution:.0f} | ${t.pnl:+.4f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Signal Distribution",
        "",
    ]

    if result.trades:
        up_trades = [t for t in result.trades if t.direction == "up"]
        down_trades = [t for t in result.trades if t.direction == "down"]
        up_wins = sum(1 for t in up_trades if t.correct_direction)
        down_wins = sum(1 for t in down_trades if t.correct_direction)

        lines += [
            "| Direction | Trades | Wins | Win Rate | Total PnL |",
            "|-----------|--------|------|----------|-----------|",
            f"| UP  | {len(up_trades)} | {up_wins} | {up_wins/max(len(up_trades),1):.1%} | ${sum(t.pnl for t in up_trades):+.2f} |",
            f"| DOWN | {len(down_trades)} | {down_wins} | {down_wins/max(len(down_trades),1):.1%} | ${sum(t.pnl for t in down_trades):+.2f} |",
            "",
            "### Entry Minute Distribution",
            "",
            "| Minute in Window | # Signals |",
            "|-----------------|-----------|",
        ]

        minute_counts: dict[int, int] = {}
        for t in result.trades:
            minute_counts[t.minute_entered] = minute_counts.get(t.minute_entered, 0) + 1
        for m in sorted(minute_counts):
            lines.append(f"| {m} | {minute_counts[m]} |")

    lines += [
        "",
        "---",
        "",
        "## Notes",
        "",
        "- **Price model:** Binary option (normal CDF). Fair price = N(return / σ_remaining).",
        "- **Entry price:** Lagged Polymarket price (60s behind Binance fair value).",
        "- **Exit:** At market resolution — 1.0 if correct direction, 0.0 if wrong.",
        "- **Cooldown:** 5 minutes between signals per symbol.",
        "- **Gamma API:** Queried for resolved BTC market metadata (informational only).",
        "- **Small sample warning:** N<30 trades. Win rate and Sharpe are not statistically",
        "  reliable at this sample size. Extend to 90+ days for meaningful estimates.",
        "- **Sharpe note:** Calculated on trade-level PnL (not daily time-series).",
        "  With few trades this is highly sensitive to outliers.",
        "- **Limitations:** Synthetic model — real Polymarket prices may differ from model.",
        "  Slippage, maker/taker fees (~2%), and liquidity not modelled.",
        "  Real Polymarket market makers update prices within seconds, not 60 seconds.",
        "  Entry filter (0.40–0.60) ensures near-neutral conditions but reduces trade count.",
        "",
    ]

    markdown = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(markdown)

    return markdown


def _fmt_date(dt) -> str:
    if dt is None:
        return "N/A"
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    return str(dt)[:10]
