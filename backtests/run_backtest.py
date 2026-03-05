"""
Backtest runner — fetches data, runs simulation, writes backtests/results.md

Usage:
    python -m backtests.run_backtest                  # 30 days, BTC
    python -m backtests.run_backtest --days 60        # 60 days
    python -m backtests.run_backtest --symbol ETH     # ETH instead
"""
import argparse
import logging
import sys
import os

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backtest.runner")


def main():
    parser = argparse.ArgumentParser(description="Lag Arbitrage Backtest Runner")
    parser.add_argument("--days", type=int, default=30, help="Days of history to test (default 30)")
    parser.add_argument("--symbol", default="BTC", choices=["BTC", "ETH", "SOL"], help="Symbol to test")
    parser.add_argument("--threshold", type=float, default=0.003, help="Binance move threshold (default 0.003)")
    parser.add_argument("--min-confidence", type=float, default=0.60, help="Min signal confidence (default 0.60)")
    parser.add_argument("--lag", type=int, default=60, help="Simulated Polymarket lag in seconds (default 60)")
    parser.add_argument("--output", default="backtests/results.md", help="Output report path")
    args = parser.parse_args()

    binance_symbol = f"{args.symbol}USDT"
    logger.info(f"Starting backtest: {args.symbol} | {args.days} days | threshold={args.threshold:.3%}")

    # 1. Fetch Binance.US klines
    from backtests.data_fetcher import fetch_binance_klines, estimate_daily_volatility, fetch_gamma_btc_markets
    logger.info(f"Fetching {args.days} days of {binance_symbol} 1-min klines from Binance.US...")
    df = fetch_binance_klines(symbol=binance_symbol, interval="1m", days_back=args.days)

    if df.empty:
        logger.error("Failed to fetch Binance.US klines — aborting")
        sys.exit(1)

    daily_vol = estimate_daily_volatility(df)
    logger.info(f"Estimated daily volatility: {daily_vol:.2%}")

    # 2. Best-effort Gamma API fetch (metadata only)
    logger.info("Querying Gamma API for resolved BTC markets (informational)...")
    gamma_markets = fetch_gamma_btc_markets()
    if gamma_markets:
        logger.info(f"Found {len(gamma_markets)} resolved BTC markets in Gamma API")
    else:
        logger.info("No tick-level Polymarket history available — using synthetic price model")

    # 3. Run backtest
    from backtests.backtester import Backtester
    bt = Backtester(
        threshold_pct=args.threshold,
        min_confidence=args.min_confidence,
        daily_vol=daily_vol,
        lag_secs=args.lag,
    )
    result = bt.run(df, symbol=args.symbol)

    # 4. Generate report
    from backtests.report import generate_report
    logger.info(f"Generating report → {args.output}")
    md = generate_report(result, output_path=args.output)

    # Print summary to console
    print("\n" + "=" * 60)
    print(f"  BACKTEST COMPLETE — {args.symbol} | {args.days} days")
    print("=" * 60)
    print(f"  Trades:        {result.num_trades}")
    print(f"  Win rate:      {result.win_rate:.1%}")
    print(f"  Total PnL:     ${result.total_pnl:+.2f}")
    print(f"  Avg PnL/trade: ${result.avg_pnl:+.4f}")
    print(f"  Sharpe:        {result.sharpe_ratio:.2f}")
    print(f"  Max drawdown:  ${result.max_drawdown:.2f}")
    print(f"  Profit factor: {result.profit_factor:.2f}")
    print(f"\n  Report written to: {args.output}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
