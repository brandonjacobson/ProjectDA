# Lag Arbitrage Backtest — Performance Report

**Generated:** 2026-03-05 04:06 UTC  
**Symbol:** BTC  
**Period:** 2026-02-03 → 2026-03-05  
**Days tested:** 31  
**15-min windows:** 2879  

---

## Strategy Parameters

| Parameter | Value |
|-----------|-------|
| Binance move threshold | 0.3% per minute |
| Lookback window | 60 seconds (1 bar) |
| Simulated Poly lag | 60 seconds |
| Min confidence | 0.60 |
| Scaling factor | 10× |
| Portfolio size | $1,000 |
| Max position | 2% ($20) |
| Market window | 15 minutes |

---

## Summary Metrics

| Metric | Value |
|--------|-------|
| Total trades | 17 |
| Win rate (correct direction) | 94.1% |
| Total PnL | $+280.23 |
| Avg PnL per trade | $+16.4843 |
| Avg edge at entry | 0.119 |
| Avg confidence | 0.71 |
| Profit factor | 22.95 |
| Sharpe ratio (ann.) | 30.88 |
| Max drawdown | $12.77 |
| Best trade | $+26.55 (2026-02-05) |
| Worst trade | $-12.77 (2026-02-05) |

---

## Daily P&L

| Date | PnL | Cumulative |
|------|-----|-----------|
| 2026-02-03 | 🟢 $+23.28 | $+23.28 |
| 2026-02-05 | 🟢 $+66.49 | $+89.77 |
| 2026-02-06 | 🟢 $+58.02 | $+147.80 |
| 2026-02-07 | 🟢 $+33.21 | $+181.01 |
| 2026-02-09 | 🟢 $+16.92 | $+197.93 |
| 2026-02-11 | 🟢 $+17.10 | $+215.03 |
| 2026-02-16 | 🟢 $+15.16 | $+230.19 |
| 2026-02-17 | 🟢 $+13.92 | $+244.11 |
| 2026-03-02 | 🟢 $+18.80 | $+262.91 |
| 2026-03-03 | 🟢 $+17.32 | $+280.23 |

---

## Trade Log

| # | Date | Min | Dir | Entry | Fair | Edge | Conf | Binance% | Resolution | PnL |
|---|------|-----|-----|-------|------|------|------|----------|------------|-----|
| 1 | 2026-02-03 | 5 | DOWN | 0.404 | 0.920 | 0.149 | 0.79 | -0.529% | ✅ 1 | $+23.2796 |
| 2 | 2026-02-05 | 4 | UP | 0.406 | 0.801 | 0.131 | 0.64 | +0.366% | ❌ 0 | $-12.7683 |
| 3 | 2026-02-05 | 4 | DOWN | 0.415 | 0.980 | 0.165 | 0.94 | -0.794% | ✅ 1 | $+26.5465 |
| 4 | 2026-02-05 | 11 | DOWN | 0.419 | 0.968 | 0.123 | 0.64 | -0.421% | ✅ 1 | $+17.7992 |
| 5 | 2026-02-05 | 9 | DOWN | 0.404 | 0.978 | 0.152 | 0.81 | -0.561% | ✅ 1 | $+23.9593 |
| 6 | 2026-02-05 | 2 | UP | 0.557 | 0.980 | 0.057 | 0.69 | +1.144% | ✅ 1 | $+10.9574 |
| 7 | 2026-02-06 | 3 | UP | 0.407 | 0.892 | 0.145 | 0.77 | +0.518% | ✅ 1 | $+22.4381 |
| 8 | 2026-02-06 | 8 | DOWN | 0.419 | 0.882 | 0.118 | 0.60 | -0.374% | ✅ 1 | $+16.6908 |
| 9 | 2026-02-06 | 3 | UP | 0.413 | 0.834 | 0.129 | 0.66 | +0.420% | ✅ 1 | $+18.8941 |
| 10 | 2026-02-07 | 4 | UP | 0.462 | 0.977 | 0.108 | 0.75 | +0.702% | ✅ 1 | $+17.4186 |
| 11 | 2026-02-07 | 7 | UP | 0.433 | 0.904 | 0.110 | 0.60 | +0.424% | ✅ 1 | $+15.7941 |
| 12 | 2026-02-09 | 1 | UP | 0.500 | 0.980 | 0.104 | 0.85 | +1.039% | ✅ 1 | $+16.9234 |
| 13 | 2026-02-11 | 4 | DOWN | 0.414 | 0.797 | 0.122 | 0.60 | -0.355% | ✅ 1 | $+17.0963 |
| 14 | 2026-02-16 | 5 | UP | 0.500 | 0.980 | 0.085 | 0.76 | +0.853% | ✅ 1 | $+15.1640 |
| 15 | 2026-02-17 | 2 | DOWN | 0.500 | 0.980 | 0.078 | 0.70 | -0.783% | ✅ 1 | $+13.9177 |
| 16 | 2026-03-02 | 10 | UP | 0.404 | 0.904 | 0.132 | 0.64 | +0.355% | ✅ 1 | $+18.7987 |
| 17 | 2026-03-03 | 10 | UP | 0.410 | 0.892 | 0.124 | 0.60 | +0.337% | ✅ 1 | $+17.3238 |

---

## Signal Distribution

| Direction | Trades | Wins | Win Rate | Total PnL |
|-----------|--------|------|----------|-----------|
| UP  | 10 | 9 | 90.0% | $+140.94 |
| DOWN | 7 | 7 | 100.0% | $+139.29 |

### Entry Minute Distribution

| Minute in Window | # Signals |
|-----------------|-----------|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 4 |
| 5 | 2 |
| 7 | 1 |
| 8 | 1 |
| 9 | 1 |
| 10 | 2 |
| 11 | 1 |

---

## Notes

- **Price model:** Binary option (normal CDF). Fair price = N(return / σ_remaining).
- **Entry price:** Lagged Polymarket price (60s behind Binance fair value).
- **Exit:** At market resolution — 1.0 if correct direction, 0.0 if wrong.
- **Cooldown:** 5 minutes between signals per symbol.
- **Gamma API:** Queried for resolved BTC market metadata (informational only).
- **Small sample warning:** N<30 trades. Win rate and Sharpe are not statistically
  reliable at this sample size. Extend to 90+ days for meaningful estimates.
- **Sharpe note:** Calculated on trade-level PnL (not daily time-series).
  With few trades this is highly sensitive to outliers.
- **Limitations:** Synthetic model — real Polymarket prices may differ from model.
  Slippage, maker/taker fees (~2%), and liquidity not modelled.
  Real Polymarket market makers update prices within seconds, not 60 seconds.
  Entry filter (0.40–0.60) ensures near-neutral conditions but reduces trade count.
