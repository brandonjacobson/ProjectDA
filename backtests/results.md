# Lag Arbitrage Backtest — Execution Realism Analysis

**Generated:** 2026-03-05 04:37 UTC  
**Symbol:** BTC  
**Period:** 2026-02-03 → 2026-03-05  
**Days tested:** 31  
**15-min windows:** 2879  

---

## Why Execution Realism Matters

The optimistic baseline assumes instant fills at the stale market price.
In practice, three frictions erode the edge:

| Friction | Source | Effect |
|----------|--------|--------|
| **Execution delay** | Network latency + order routing | Price starts moving before fill |
| **Market impact** | Faster bots front-running same signal | Fill price moves toward fair value |
| **Fill probability** | Thin orderbook depth | Orders sometimes not matched |

Realistic setup (Oracle Cloud bot): ~500ms–2s delay, 30–60% market impact,
65% fill rate. Co-located HFT: 50–200ms delay, ~10% impact.

---

## Scenario Definitions

| Parameter | Optimistic | Realistic | Pessimistic |
|-----------|-----------|-----------|-------------|
| Execution delay | 0.0s | 1.5s | 3.0s |
| Market impact | 0% | 30% | 60% |
| Fill probability | 100% | 65% | 40% |

---

## Side-by-Side Performance

| Metric | Optimistic | Realistic | Pessimistic |
|--------|-----------|-----------|-------------|
| Signals attempted | 22 | 22 | 22 |
| Trades filled | 22 | 16 | 10 |
| Fill rate | 100.0% | 72.7% | 45.5% |
| Win rate | 81.8% | 81.2% | 80.0% |
| **Total PnL (gross)** | **$+268.56** | **$+163.94** | **$+83.32** |
| Total fees paid | $17.91 | $12.23 | $7.30 |
| **Total PnL (net)** | **$+245.28** | **$+148.43** | **$+74.36** |
| Fee drag | 6.7% of gross | 7.5% of gross | 8.8% of gross |
| Avg PnL / trade (gross) | $+12.21 | $+10.25 | $+8.33 |
| Avg PnL / trade (net) | $+11.15 | $+9.28 | $+7.44 |
| Avg edge (pre-fill) | 0.118 | 0.118 | 0.122 |
| Avg edge (post-fill) | 0.118 | 0.083 | 0.049 |
| Profit factor (gross) | 5.89 | 5.21 | 4.15 |
| Profit factor (net) | 5.46 | 4.81 | 3.81 |
| Max drawdown (gross) | $30.20 | $14.22 | $14.22 |
| Max drawdown (net) | $30.20 | $14.22 | $14.22 |
| Sharpe gross (ann.) | 14.93 | 13.88 | 11.54 |
| Sharpe net (ann.) | 14.22 | 13.12 | 10.75 |

---

## PnL Impact of Execution Realism + Fees

```
Optimistic   gross |██████████████████████████████████████| $+268.56
Optimistic   net   |██████████████████████████████████░░░░| $+245.28

Realistic    gross |███████████████████████░░░░░░░░░░░░░░░| $+163.94
Realistic    net   |█████████████████████░░░░░░░░░░░░░░░░░| $+148.43

Pessimistic  gross |███████████░░░░░░░░░░░░░░░░░░░░░░░░░░░| $+83.32
Pessimistic  net   |██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░| $+74.36

```

---

## Optimistic Scenario — Detail

*Execution delay: 0.0s | Market impact: 0% | Fill probability: 100%*

### Daily P&L

| Date | PnL | Cumulative |
|------|-----|-----------|
| 2026-02-05 | 🟢 $+0.28 | $+0.28 |
| 2026-02-06 | 🟢 $+87.84 | $+88.12 |
| 2026-02-07 | 🟢 $+35.25 | $+123.36 |
| 2026-02-16 | 🟢 $+15.16 | $+138.53 |
| 2026-02-17 | 🟢 $+33.30 | $+171.83 |
| 2026-02-24 | 🟢 $+20.63 | $+192.46 |
| 2026-03-01 | 🟢 $+45.13 | $+237.59 |
| 2026-03-02 | 🟢 $+17.59 | $+255.18 |
| 2026-03-04 | 🟢 $+13.38 | $+268.56 |

### Trade Log

| # | Date | Min | Dir | Fill | Edge→Post | Result | Gross | Fees | Net |
|---|------|-----|-----|------|-----------|--------|-------|------|-----|
| 1 | 2026-02-05 | 3 | UP | 0.410 | 0.127→0.127 | ❌ | $-12.53 | $0.25 | $-12.53 |
| 2 | 2026-02-05 | 13 | UP | 0.410 | 0.159→0.159 | ✅ | $+25.38 | $1.20 | $+23.68 |
| 3 | 2026-02-05 | 1 | UP | 0.500 | 0.114→0.114 | ✅ | $+17.62 | $1.04 | $+16.23 |
| 4 | 2026-02-05 | 4 | DOWN | 0.404 | 0.140→0.140 | ❌ | $-14.22 | $0.28 | $-14.22 |
| 5 | 2026-02-05 | 2 | UP | 0.426 | 0.136→0.136 | ❌ | $-15.99 | $0.32 | $-15.99 |
| 6 | 2026-02-06 | 1 | DOWN | 0.500 | 0.090→0.090 | ✅ | $+15.95 | $0.94 | $+14.69 |
| 7 | 2026-02-06 | 1 | UP | 0.500 | 0.085→0.085 | ✅ | $+15.11 | $0.89 | $+13.92 |
| 8 | 2026-02-06 | 1 | UP | 0.500 | 0.082→0.082 | ✅ | $+14.52 | $0.86 | $+13.37 |
| 9 | 2026-02-06 | 2 | UP | 0.410 | 0.141→0.141 | ✅ | $+21.81 | $1.03 | $+20.35 |
| 10 | 2026-02-06 | 10 | UP | 0.407 | 0.126→0.126 | ✅ | $+17.67 | $0.83 | $+16.49 |
| 11 | 2026-02-06 | 4 | DOWN | 0.423 | 0.117→0.117 | ❌ | $-12.23 | $0.24 | $-12.23 |
| 12 | 2026-02-06 | 4 | DOWN | 0.461 | 0.097→0.097 | ✅ | $+15.00 | $0.80 | $+13.90 |
| 13 | 2026-02-07 | 5 | DOWN | 0.414 | 0.125→0.125 | ✅ | $+18.04 | $0.86 | $+16.82 |
| 14 | 2026-02-07 | 3 | UP | 0.464 | 0.106→0.106 | ✅ | $+17.20 | $0.93 | $+15.93 |
| 15 | 2026-02-16 | 4 | UP | 0.500 | 0.085→0.085 | ✅ | $+15.16 | $0.90 | $+13.96 |
| 16 | 2026-02-17 | 1 | DOWN | 0.500 | 0.078→0.078 | ✅ | $+13.92 | $0.82 | $+12.82 |
| 17 | 2026-02-17 | 9 | UP | 0.430 | 0.126→0.126 | ✅ | $+19.39 | $0.96 | $+18.04 |
| 18 | 2026-02-24 | 10 | DOWN | 0.421 | 0.134→0.134 | ✅ | $+20.63 | $1.00 | $+19.22 |
| 19 | 2026-03-01 | 6 | UP | 0.426 | 0.183→0.183 | ✅ | $+26.96 | $1.32 | $+25.10 |
| 20 | 2026-03-01 | 4 | DOWN | 0.405 | 0.129→0.129 | ✅ | $+18.16 | $0.85 | $+16.95 |
| 21 | 2026-03-02 | 9 | UP | 0.411 | 0.125→0.125 | ✅ | $+17.59 | $0.83 | $+16.41 |
| 22 | 2026-03-04 | 4 | UP | 0.479 | 0.082→0.082 | ✅ | $+13.38 | $0.75 | $+12.36 |

### Direction Breakdown

| Dir | Trades | Wins | Win% | PnL |
|-----|--------|------|------|-----|
| UP | 14 | 12 | 85.7% | $+193.31 |
| DOWN | 8 | 6 | 75.0% | $+75.25 |

---

## Realistic Scenario — Detail

*Execution delay: 1.5s | Market impact: 30% | Fill probability: 65%*

### Daily P&L

| Date | PnL | Cumulative |
|------|-----|-----------|
| 2026-02-05 | 🟢 $+9.53 | $+9.53 |
| 2026-02-06 | 🟢 $+47.77 | $+57.29 |
| 2026-02-07 | 🟢 $+30.61 | $+87.91 |
| 2026-02-16 | 🟢 $+13.69 | $+101.59 |
| 2026-02-17 | 🟢 $+29.31 | $+130.90 |
| 2026-02-24 | 🟢 $+17.53 | $+148.44 |
| 2026-03-01 | 🟢 $+15.50 | $+163.94 |

### Trade Log

| # | Date | Min | Dir | Fill | Edge→Post | Result | Gross | Fees | Net |
|---|------|-----|-----|------|-----------|--------|-------|------|-----|
| 1 | 2026-02-05 | 3 | UP | 0.448 | 0.127→0.089 | ❌ | $-12.53 | $0.25 | $-12.53 |
| 2 | 2026-02-05 | 13 | UP | 0.458 | 0.159→0.111 | ✅ | $+20.91 | $1.11 | $+19.38 |
| 3 | 2026-02-05 | 1 | UP | 0.534 | 0.114→0.080 | ✅ | $+15.36 | $1.00 | $+14.05 |
| 4 | 2026-02-05 | 4 | DOWN | 0.446 | 0.140→0.098 | ❌ | $-14.22 | $0.28 | $-14.22 |
| 5 | 2026-02-06 | 1 | UP | 0.525 | 0.082→0.057 | ✅ | $+13.17 | $0.83 | $+12.07 |
| 6 | 2026-02-06 | 2 | UP | 0.453 | 0.141→0.099 | ✅ | $+18.35 | $0.96 | $+17.02 |
| 7 | 2026-02-06 | 10 | UP | 0.445 | 0.126→0.088 | ✅ | $+15.13 | $0.78 | $+14.05 |
| 8 | 2026-02-06 | 4 | DOWN | 0.458 | 0.117→0.082 | ❌ | $-12.23 | $0.24 | $-12.23 |
| 9 | 2026-02-06 | 4 | DOWN | 0.490 | 0.097→0.068 | ✅ | $+13.35 | $0.77 | $+12.32 |
| 10 | 2026-02-07 | 5 | DOWN | 0.452 | 0.125→0.088 | ✅ | $+15.48 | $0.81 | $+14.36 |
| 11 | 2026-02-07 | 3 | UP | 0.496 | 0.106→0.074 | ✅ | $+15.14 | $0.89 | $+13.95 |
| 12 | 2026-02-16 | 4 | UP | 0.526 | 0.085→0.060 | ✅ | $+13.69 | $0.87 | $+12.54 |
| 13 | 2026-02-17 | 1 | DOWN | 0.523 | 0.078→0.055 | ✅ | $+12.67 | $0.80 | $+11.62 |
| 14 | 2026-02-17 | 9 | UP | 0.468 | 0.126→0.088 | ✅ | $+16.64 | $0.91 | $+15.40 |
| 15 | 2026-02-24 | 10 | DOWN | 0.461 | 0.134→0.094 | ✅ | $+17.53 | $0.94 | $+16.24 |
| 16 | 2026-03-01 | 4 | DOWN | 0.444 | 0.129→0.090 | ✅ | $+15.50 | $0.79 | $+14.40 |

### Direction Breakdown

| Dir | Trades | Wins | Win% | PnL |
|-----|--------|------|------|-----|
| UP | 9 | 8 | 88.9% | $+115.86 |
| DOWN | 7 | 5 | 71.4% | $+48.08 |

---

## Pessimistic Scenario — Detail

*Execution delay: 3.0s | Market impact: 60% | Fill probability: 40%*

### Daily P&L

| Date | PnL | Cumulative |
|------|-----|-----------|
| 2026-02-05 | 🟢 $+16.43 | $+16.43 |
| 2026-02-06 | 🟢 $+12.69 | $+29.12 |
| 2026-02-07 | 🟢 $+26.63 | $+55.75 |
| 2026-02-17 | 🟢 $+14.30 | $+70.05 |
| 2026-03-01 | 🟢 $+13.27 | $+83.32 |

### Trade Log

| # | Date | Min | Dir | Fill | Edge→Post | Result | Gross | Fees | Net |
|---|------|-----|-----|------|-----------|--------|-------|------|-----|
| 1 | 2026-02-05 | 13 | UP | 0.506 | 0.159→0.063 | ✅ | $+17.28 | $1.04 | $+15.90 |
| 2 | 2026-02-05 | 1 | UP | 0.569 | 0.114→0.046 | ✅ | $+13.37 | $0.96 | $+12.14 |
| 3 | 2026-02-05 | 4 | DOWN | 0.488 | 0.140→0.056 | ❌ | $-14.22 | $0.28 | $-14.22 |
| 4 | 2026-02-06 | 1 | UP | 0.549 | 0.082→0.033 | ✅ | $+11.93 | $0.81 | $+10.88 |
| 5 | 2026-02-06 | 10 | UP | 0.483 | 0.126→0.051 | ✅ | $+12.99 | $0.73 | $+12.00 |
| 6 | 2026-02-06 | 4 | DOWN | 0.493 | 0.117→0.047 | ❌ | $-12.23 | $0.24 | $-12.23 |
| 7 | 2026-02-07 | 5 | DOWN | 0.489 | 0.125→0.050 | ✅ | $+13.31 | $0.77 | $+12.27 |
| 8 | 2026-02-07 | 3 | UP | 0.528 | 0.106→0.043 | ✅ | $+13.32 | $0.85 | $+12.21 |
| 9 | 2026-02-17 | 9 | UP | 0.506 | 0.126→0.050 | ✅ | $+14.30 | $0.86 | $+13.16 |
| 10 | 2026-03-01 | 4 | DOWN | 0.482 | 0.129→0.052 | ✅ | $+13.27 | $0.75 | $+12.25 |

### Direction Breakdown

| Dir | Trades | Wins | Win% | PnL |
|-----|--------|------|------|-----|
| UP | 6 | 6 | 100.0% | $+83.20 |
| DOWN | 4 | 2 | 50.0% | $+0.12 |

---

## Methodology Notes

- **Price model:** Binary option (normal CDF). P(UP) = N(cumulative_return / σ_remaining).
- **Lag model:** Polymarket price = fair value from `lag_secs` ago (default 60s).
- **Market impact:** `fill_price = lagged_price + impact_pct × strat_edge`
  Simulates other bots buying the same side before our order lands.
- **Fill probability:** Bernoulli draw per signal. Missed fills still trigger cooldown.
- **Entry filter:** 0.40–0.60 price range — genuine lag opportunity zone near window open.
- **Cooldown:** 5 minutes between signals to avoid overtrading.
- **Fees:** Not modelled. Polymarket charges ~2% maker/taker. Subtract from PnL.
- **Small sample warning:** N<30 per scenario. Extend to 90+ days for reliable stats.
- **Reproducibility:** Fixed random seed (42) per scenario for fill probability draws.
