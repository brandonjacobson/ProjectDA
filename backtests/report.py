"""
Backtest report generator — single scenario and multi-scenario comparison.
Writes to backtests/results.md
"""
import os
from datetime import datetime, timezone
from typing import Optional

from backtests.backtester import BacktestResult


# ---------------------------------------------------------------------------
# Multi-scenario comparison (primary entry point)
# ---------------------------------------------------------------------------

def generate_comparison_report(
    scenarios: list[BacktestResult],
    output_path: str = "backtests/results.md",
) -> str:
    """
    Generate a side-by-side comparison of multiple scenarios plus per-scenario
    detail sections. Writes to output_path and returns markdown string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ref = scenarios[0]  # use first for header metadata

    lines = [
        "# Lag Arbitrage Backtest — Execution Realism Analysis",
        "",
        f"**Generated:** {now}  ",
        f"**Symbol:** {ref.symbol}  ",
        f"**Period:** {_fmt_date(ref.start_date)} → {_fmt_date(ref.end_date)}  ",
        f"**Days tested:** {ref.days_tested}  ",
        f"**15-min windows:** {ref.windows_tested}  ",
        "",
        "---",
        "",
        "## Why Execution Realism Matters",
        "",
        "The optimistic baseline assumes instant fills at the stale market price.",
        "In practice, three frictions erode the edge:",
        "",
        "| Friction | Source | Effect |",
        "|----------|--------|--------|",
        "| **Execution delay** | Network latency + order routing | Price starts moving before fill |",
        "| **Market impact** | Faster bots front-running same signal | Fill price moves toward fair value |",
        "| **Fill probability** | Thin orderbook depth | Orders sometimes not matched |",
        "",
        "Realistic setup (Oracle Cloud bot): ~500ms–2s delay, 30–60% market impact,",
        "65% fill rate. Co-located HFT: 50–200ms delay, ~10% impact.",
        "",
        "---",
        "",
        "## Scenario Definitions",
        "",
        "| Parameter | Optimistic | Realistic | Pessimistic |",
        "|-----------|-----------|-----------|-------------|",
    ]

    params = [
        ("Execution delay", "execution_delay_secs", lambda v: f"{v:.1f}s"),
        ("Market impact", "market_impact_pct", lambda v: f"{v:.0%}"),
        ("Fill probability", "fill_probability", lambda v: f"{v:.0%}"),
    ]
    for label, attr, fmt in params:
        vals = " | ".join(fmt(getattr(s, attr)) for s in scenarios)
        lines.append(f"| {label} | {vals} |")

    lines += [
        "",
        "---",
        "",
        "## Side-by-Side Performance",
        "",
        "| Metric | Optimistic | Realistic | Pessimistic |",
        "|--------|-----------|-----------|-------------|",
    ]

    metrics = [
        ("Signals attempted",    lambda r: str(r.num_trades + r.attempted_signals)),
        ("Trades filled",        lambda r: str(r.num_trades)),
        ("Fill rate",            lambda r: f"{r.fill_rate:.1%}"),
        ("Win rate",             lambda r: f"{r.win_rate:.1%}"),
        ("Total PnL",            lambda r: f"${r.total_pnl:+.2f}"),
        ("Avg PnL / trade",      lambda r: f"${r.avg_pnl:+.2f}"),
        ("Avg edge (pre-fill)",  lambda r: f"{r.avg_edge_pre_impact:.3f}"),
        ("Avg edge (post-fill)", lambda r: f"{r.avg_edge_post_impact:.3f}"),
        ("Profit factor",        lambda r: f"{r.profit_factor:.2f}" if r.trades else "N/A"),
        ("Max drawdown",         lambda r: f"${r.max_drawdown:.2f}"),
        ("Sharpe (ann.)",        lambda r: f"{r.sharpe_ratio:.2f}" if len(r.trades) > 1 else "N/A"),
    ]

    for label, fn in metrics:
        vals = " | ".join(fn(s) for s in scenarios)
        lines.append(f"| {label} | {vals} |")

    # Visual PnL comparison bar chart (ASCII)
    lines += [
        "",
        "---",
        "",
        "## PnL Impact of Execution Realism",
        "",
        "```",
    ]
    max_pnl = max((s.total_pnl for s in scenarios), default=1.0)
    bar_width = 40
    for s in scenarios:
        pnl = s.total_pnl
        filled_bars = int(max(pnl / max_pnl, 0) * bar_width) if max_pnl > 0 else 0
        bar = "█" * filled_bars + "░" * (bar_width - filled_bars)
        label = s.scenario_name.capitalize().ljust(12)
        lines.append(f"{label} |{bar}| ${pnl:+.2f}")
    lines.append("```")

    # Per-scenario detail sections
    for s in scenarios:
        lines += _scenario_detail(s)

    # Notes
    lines += [
        "",
        "---",
        "",
        "## Methodology Notes",
        "",
        "- **Price model:** Binary option (normal CDF). P(UP) = N(cumulative_return / σ_remaining).",
        "- **Lag model:** Polymarket price = fair value from `lag_secs` ago (default 60s).",
        "- **Market impact:** `fill_price = lagged_price + impact_pct × strat_edge`",
        "  Simulates other bots buying the same side before our order lands.",
        "- **Fill probability:** Bernoulli draw per signal. Missed fills still trigger cooldown.",
        "- **Entry filter:** 0.40–0.60 price range — genuine lag opportunity zone near window open.",
        "- **Cooldown:** 5 minutes between signals to avoid overtrading.",
        "- **Fees:** Not modelled. Polymarket charges ~2% maker/taker. Subtract from PnL.",
        "- **Small sample warning:** N<30 per scenario. Extend to 90+ days for reliable stats.",
        "- **Reproducibility:** Fixed random seed (42) per scenario for fill probability draws.",
        "",
    ]

    markdown = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(markdown)

    return markdown


def _scenario_detail(result: BacktestResult) -> list[str]:
    """Return lines for a single scenario's detailed breakdown."""
    title = result.scenario_name.capitalize()
    lines = [
        "",
        "---",
        "",
        f"## {title} Scenario — Detail",
        "",
        f"*Execution delay: {result.execution_delay_secs:.1f}s | "
        f"Market impact: {result.market_impact_pct:.0%} | "
        f"Fill probability: {result.fill_probability:.0%}*",
        "",
    ]

    if not result.trades:
        lines.append("*No trades filled under these conditions.*")
        return lines

    # Daily P&L
    lines += [
        "### Daily P&L",
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

    # Trade log
    lines += [
        "",
        "### Trade Log",
        "",
        "| # | Date | Min | Dir | Lagged | Fill | Edge→Fill | Conf | Binance% | Result | PnL |",
        "|---|------|-----|-----|--------|------|-----------|------|----------|--------|-----|",
    ]
    for i, t in enumerate(result.trades, 1):
        lines.append(
            f"| {i} | {_fmt_date(t.window_start)} | {t.minute_entered} "
            f"| {t.direction.upper()} | {t.entry_price:.3f} | {t.actual_fill_price:.3f} "
            f"| {t.edge_at_entry:.3f}→{t.edge_after_impact:.3f} | {t.confidence:.2f} "
            f"| {t.binance_move_pct:+.3%} "
            f"| {'✅' if t.correct_direction else '❌'} | ${t.pnl:+.4f} |"
        )

    # Direction breakdown
    up_trades = [t for t in result.trades if t.direction == "up"]
    down_trades = [t for t in result.trades if t.direction == "down"]
    up_wins = sum(1 for t in up_trades if t.correct_direction)
    down_wins = sum(1 for t in down_trades if t.correct_direction)

    lines += [
        "",
        "### Direction Breakdown",
        "",
        "| Dir | Trades | Wins | Win% | PnL |",
        "|-----|--------|------|------|-----|",
        f"| UP | {len(up_trades)} | {up_wins} | {up_wins/max(len(up_trades),1):.1%} | ${sum(t.pnl for t in up_trades):+.2f} |",
        f"| DOWN | {len(down_trades)} | {down_wins} | {down_wins/max(len(down_trades),1):.1%} | ${sum(t.pnl for t in down_trades):+.2f} |",
    ]

    return lines


# ---------------------------------------------------------------------------
# Single-scenario report (kept for backwards compat / standalone use)
# ---------------------------------------------------------------------------

def generate_report(result: BacktestResult, output_path: str = "backtests/results.md") -> str:
    """Generate a single-scenario report. Wraps generate_comparison_report."""
    return generate_comparison_report([result], output_path=output_path)


def _fmt_date(dt) -> str:
    if dt is None:
        return "N/A"
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    return str(dt)[:10]
