"""
Backtest runner — fetches data, runs all three execution scenarios, writes results.md

Usage:
    python -m backtests.run_backtest                  # 30 days, BTC
    python -m backtests.run_backtest --days 60        # 60 days
    python -m backtests.run_backtest --symbol ETH
    python -m backtests.run_backtest --scenario realistic   # single scenario only
"""
import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backtest.runner")

from backtests.backtester import (
    Backtester,
    SCENARIO_OPTIMISTIC,
    SCENARIO_REALISTIC,
    SCENARIO_PESSIMISTIC,
)


def run_scenario(df, daily_vol, symbol, scenario_cfg, base_kwargs) -> "BacktestResult":
    bt = Backtester(**base_kwargs, **scenario_cfg)
    return bt.run(df, symbol=symbol)


def _print_summary(label: str, r) -> None:
    print(f"\n  ── {label.upper()} ──")
    print(f"  Signals:    {r.num_trades + r.attempted_signals}  "
          f"Filled: {r.num_trades}  Fill rate: {r.fill_rate:.0%}")
    print(f"  Win rate:   {r.win_rate:.1%}")
    print(f"  Total PnL:  ${r.total_pnl:+.2f}")
    print(f"  Max DD:     ${r.max_drawdown:.2f}")
    print(f"  Avg edge:   {r.avg_edge_pre_impact:.3f} → {r.avg_edge_post_impact:.3f} (post-fill)")


def main():
    parser = argparse.ArgumentParser(description="Lag Arbitrage Backtest Runner")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--symbol", default="BTC", choices=["BTC", "ETH", "SOL"])
    parser.add_argument("--threshold", type=float, default=0.003)
    parser.add_argument("--min-confidence", type=float, default=0.60)
    parser.add_argument("--lag", type=int, default=60)
    parser.add_argument("--output", default="backtests/results.md")
    parser.add_argument(
        "--scenario",
        choices=["all", "optimistic", "realistic", "pessimistic"],
        default="all",
        help="Which scenario(s) to run (default: all three)",
    )
    args = parser.parse_args()

    binance_symbol = f"{args.symbol}USDT"
    logger.info(f"Starting backtest: {args.symbol} | {args.days} days | "
                f"threshold={args.threshold:.3%} | scenario={args.scenario}")

    # 1. Fetch Binance.US klines (shared across all scenarios)
    from backtests.data_fetcher import (
        fetch_binance_klines, estimate_daily_volatility, fetch_gamma_btc_markets
    )
    logger.info(f"Fetching {args.days} days of {binance_symbol} 1-min klines from Binance.US...")
    df = fetch_binance_klines(symbol=binance_symbol, interval="1m", days_back=args.days)

    if df.empty:
        logger.error("Failed to fetch Binance.US klines — aborting")
        sys.exit(1)

    daily_vol = estimate_daily_volatility(df)
    logger.info(f"Estimated daily volatility: {daily_vol:.2%}")

    logger.info("Querying Gamma API for resolved BTC markets (informational)...")
    gamma_markets = fetch_gamma_btc_markets()
    if gamma_markets:
        logger.info(f"Found {len(gamma_markets)} resolved BTC markets in Gamma API")
    else:
        logger.info("No tick-level Polymarket history available — using synthetic price model")

    # 2. Base kwargs shared across scenarios
    base_kwargs = dict(
        threshold_pct=args.threshold,
        min_confidence=args.min_confidence,
        daily_vol=daily_vol,
        lag_secs=args.lag,
    )

    # 3. Run scenario(s)
    scenario_map = {
        "optimistic": SCENARIO_OPTIMISTIC,
        "realistic": SCENARIO_REALISTIC,
        "pessimistic": SCENARIO_PESSIMISTIC,
    }

    if args.scenario == "all":
        configs = [SCENARIO_OPTIMISTIC, SCENARIO_REALISTIC, SCENARIO_PESSIMISTIC]
    else:
        configs = [scenario_map[args.scenario]]

    results = []
    for cfg in configs:
        logger.info(f"Running {cfg['scenario_name']} scenario...")
        r = run_scenario(df, daily_vol, args.symbol, cfg, base_kwargs)
        results.append(r)

    # 4. Generate report
    from backtests.report import generate_comparison_report
    logger.info(f"Generating report → {args.output}")
    generate_comparison_report(results, output_path=args.output)

    # 5. Console summary
    print("\n" + "=" * 60)
    print(f"  BACKTEST COMPLETE — {args.symbol} | {args.days} days")
    print("=" * 60)
    for r in results:
        _print_summary(r.scenario_name, r)
    print(f"\n  Report written to: {args.output}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
