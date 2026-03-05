# Lag Arbitrage Backtest — Execution Realism Analysis

**Generated:** 2026-03-05 04:23 UTC  
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
| Signals attempted | 16 | 16 | 16 |
| Trades filled | 16 | 13 | 8 |
| Fill rate | 100.0% | 81.2% | 50.0% |
| Win rate | 87.5% | 84.6% | 87.5% |
| Total PnL | $+208.25 | $+139.53 | $+82.26 |
| Avg PnL / trade | $+13.02 | $+10.73 | $+10.28 |
| Avg edge (pre-fill) | 0.111 | 0.116 | 0.123 |
| Avg edge (post-fill) | 0.111 | 0.081 | 0.049 |
| Profit factor | 8.89 | 6.29 | 7.08 |
| Max drawdown | $13.53 | $13.53 | $13.53 |
| Sharpe (ann.) | 19.38 | 15.72 | 16.70 |

---

## PnL Impact of Execution Realism

```
Optimistic   |████████████████████████████████████████| $+208.25
Realistic    |██████████████████████████░░░░░░░░░░░░░░| $+139.53
Pessimistic  |███████████████░░░░░░░░░░░░░░░░░░░░░░░░░| $+82.26
```

---

## Optimistic Scenario — Detail

*Execution delay: 0.0s | Market impact: 0% | Fill probability: 100%*

### Daily P&L

| Date | PnL | Cumulative |
|------|-----|-----------|
| 2026-02-03 | 🟢 $+18.04 | $+18.04 |
| 2026-02-04 | 🔴 $-13.53 | $+4.51 |
| 2026-02-05 | 🟢 $+34.70 | $+39.21 |
| 2026-02-06 | 🟢 $+16.23 | $+55.44 |
| 2026-02-07 | 🟢 $+11.99 | $+67.43 |
| 2026-02-16 | 🟢 $+15.16 | $+82.59 |
| 2026-02-24 | 🟢 $+17.15 | $+99.75 |
| 2026-02-25 | 🟢 $+50.30 | $+150.05 |
| 2026-02-26 | 🔴 $-12.84 | $+137.20 |
| 2026-02-28 | 🟢 $+19.57 | $+156.77 |
| 2026-03-01 | 🟢 $+38.19 | $+194.97 |
| 2026-03-04 | 🟢 $+13.28 | $+208.25 |

### Trade Log

| # | Date | Min | Dir | Lagged | Fill | Edge→Fill | Conf | Binance% | Result | PnL |
|---|------|-----|-----|--------|------|-----------|------|----------|--------|-----|
| 1 | 2026-02-03 | 13 | UP | 0.409 | 0.409 | 0.127→0.127 | 0.62 | +0.362% | ✅ | $+18.0405 |
| 2 | 2026-02-04 | 4 | UP | 0.403 | 0.403 | 0.137→0.137 | 0.68 | +0.396% | ❌ | $-13.5332 |
| 3 | 2026-02-05 | 12 | UP | 0.432 | 0.432 | 0.137→0.137 | 0.84 | +0.691% | ✅ | $+22.0503 |
| 4 | 2026-02-05 | 1 | UP | 0.500 | 0.500 | 0.071→0.071 | 0.63 | +0.712% | ✅ | $+12.6531 |
| 5 | 2026-02-06 | 3 | DOWN | 0.426 | 0.426 | 0.114→0.114 | 0.60 | -0.399% | ✅ | $+16.2323 |
| 6 | 2026-02-07 | 2 | UP | 0.504 | 0.504 | 0.066→0.066 | 0.61 | +0.702% | ✅ | $+11.9872 |
| 7 | 2026-02-16 | 3 | UP | 0.500 | 0.500 | 0.085→0.085 | 0.76 | +0.853% | ✅ | $+15.1640 |
| 8 | 2026-02-24 | 9 | DOWN | 0.442 | 0.442 | 0.113→0.113 | 0.68 | -0.549% | ✅ | $+17.1523 |
| 9 | 2026-02-25 | 2 | UP | 0.465 | 0.465 | 0.094→0.094 | 0.64 | +0.592% | ✅ | $+14.7566 |
| 10 | 2026-02-25 | 12 | DOWN | 0.426 | 0.426 | 0.114→0.114 | 0.60 | -0.396% | ✅ | $+16.1936 |
| 11 | 2026-02-25 | 4 | UP | 0.407 | 0.407 | 0.133→0.133 | 0.67 | +0.401% | ✅ | $+19.3515 |
| 12 | 2026-02-26 | 7 | DOWN | 0.419 | 0.419 | 0.123→0.123 | 0.64 | -0.420% | ❌ | $-12.8441 |
| 13 | 2026-02-28 | 12 | DOWN | 0.408 | 0.408 | 0.133→0.133 | 0.67 | -0.413% | ✅ | $+19.5703 |
| 14 | 2026-03-01 | 10 | UP | 0.408 | 0.408 | 0.144→0.144 | 0.77 | +0.520% | ✅ | $+22.3478 |
| 15 | 2026-03-01 | 5 | UP | 0.511 | 0.511 | 0.098→0.098 | 0.83 | +1.087% | ✅ | $+15.8457 |
| 16 | 2026-03-04 | 3 | UP | 0.480 | 0.480 | 0.081→0.081 | 0.61 | +0.614% | ✅ | $+13.2785 |

### Direction Breakdown

| Dir | Trades | Wins | Win% | PnL |
|-----|--------|------|------|-----|
| UP | 11 | 10 | 90.9% | $+151.94 |
| DOWN | 5 | 4 | 80.0% | $+56.30 |

---

## Realistic Scenario — Detail

*Execution delay: 1.5s | Market impact: 30% | Fill probability: 65%*

### Daily P&L

| Date | PnL | Cumulative |
|------|-----|-----------|
| 2026-02-03 | 🟢 $+15.44 | $+15.44 |
| 2026-02-04 | 🔴 $-13.53 | $+1.91 |
| 2026-02-05 | 🟢 $+30.30 | $+32.21 |
| 2026-02-24 | 🟢 $+14.97 | $+47.18 |
| 2026-02-25 | 🟢 $+43.72 | $+90.90 |
| 2026-02-26 | 🔴 $-12.84 | $+78.06 |
| 2026-02-28 | 🟢 $+16.62 | $+94.67 |
| 2026-03-01 | 🟢 $+32.81 | $+127.48 |
| 2026-03-04 | 🟢 $+12.04 | $+139.53 |

### Trade Log

| # | Date | Min | Dir | Lagged | Fill | Edge→Fill | Conf | Binance% | Result | PnL |
|---|------|-----|-----|--------|------|-----------|------|----------|--------|-----|
| 1 | 2026-02-03 | 13 | UP | 0.409 | 0.447 | 0.127→0.089 | 0.62 | +0.362% | ✅ | $+15.4389 |
| 2 | 2026-02-04 | 4 | UP | 0.403 | 0.444 | 0.137→0.096 | 0.68 | +0.396% | ❌ | $-13.5332 |
| 3 | 2026-02-05 | 12 | UP | 0.432 | 0.473 | 0.137→0.096 | 0.84 | +0.691% | ✅ | $+18.6836 |
| 4 | 2026-02-05 | 1 | UP | 0.500 | 0.521 | 0.071→0.050 | 0.63 | +0.712% | ✅ | $+11.6167 |
| 5 | 2026-02-24 | 9 | DOWN | 0.442 | 0.476 | 0.113→0.079 | 0.68 | -0.549% | ✅ | $+14.9706 |
| 6 | 2026-02-25 | 2 | UP | 0.465 | 0.493 | 0.094→0.066 | 0.64 | +0.592% | ✅ | $+13.1808 |
| 7 | 2026-02-25 | 12 | DOWN | 0.426 | 0.460 | 0.114→0.080 | 0.60 | -0.396% | ✅ | $+14.0972 |
| 8 | 2026-02-25 | 4 | UP | 0.407 | 0.447 | 0.133→0.093 | 0.67 | +0.401% | ✅ | $+16.4448 |
| 9 | 2026-02-26 | 7 | DOWN | 0.419 | 0.456 | 0.123→0.086 | 0.64 | -0.420% | ❌ | $-12.8441 |
| 10 | 2026-02-28 | 12 | DOWN | 0.408 | 0.448 | 0.133→0.093 | 0.67 | -0.413% | ✅ | $+16.6173 |
| 11 | 2026-03-01 | 10 | UP | 0.408 | 0.451 | 0.144→0.101 | 0.77 | +0.520% | ✅ | $+18.7294 |
| 12 | 2026-03-01 | 5 | UP | 0.511 | 0.540 | 0.098→0.069 | 0.83 | +1.087% | ✅ | $+14.0825 |
| 13 | 2026-03-04 | 3 | UP | 0.480 | 0.504 | 0.081→0.057 | 0.61 | +0.614% | ✅ | $+12.0411 |

### Direction Breakdown

| Dir | Trades | Wins | Win% | PnL |
|-----|--------|------|------|-----|
| UP | 9 | 8 | 88.9% | $+106.68 |
| DOWN | 4 | 3 | 75.0% | $+32.84 |

---

## Pessimistic Scenario — Detail

*Execution delay: 3.0s | Market impact: 60% | Fill probability: 40%*

### Daily P&L

| Date | PnL | Cumulative |
|------|-----|-----------|
| 2026-02-04 | 🔴 $-13.53 | $-13.53 |
| 2026-02-05 | 🟢 $+26.52 | $+12.98 |
| 2026-02-24 | 🟢 $+13.08 | $+26.06 |
| 2026-02-25 | 🟢 $+26.30 | $+52.36 |
| 2026-02-28 | 🟢 $+14.15 | $+66.51 |
| 2026-03-01 | 🟢 $+15.74 | $+82.26 |

### Trade Log

| # | Date | Min | Dir | Lagged | Fill | Edge→Fill | Conf | Binance% | Result | PnL |
|---|------|-----|-----|--------|------|-----------|------|----------|--------|-----|
| 1 | 2026-02-04 | 4 | UP | 0.403 | 0.485 | 0.137→0.055 | 0.68 | +0.396% | ❌ | $-13.5332 |
| 2 | 2026-02-05 | 12 | UP | 0.432 | 0.514 | 0.137→0.055 | 0.84 | +0.691% | ✅ | $+15.8540 |
| 3 | 2026-02-05 | 1 | UP | 0.500 | 0.543 | 0.071→0.028 | 0.63 | +0.712% | ✅ | $+10.6618 |
| 4 | 2026-02-24 | 9 | DOWN | 0.442 | 0.510 | 0.113→0.045 | 0.68 | -0.549% | ✅ | $+13.0778 |
| 5 | 2026-02-25 | 12 | DOWN | 0.426 | 0.494 | 0.114→0.046 | 0.60 | -0.396% | ✅ | $+12.2910 |
| 6 | 2026-02-25 | 4 | UP | 0.407 | 0.487 | 0.133→0.053 | 0.67 | +0.401% | ✅ | $+14.0133 |
| 7 | 2026-02-28 | 12 | DOWN | 0.408 | 0.488 | 0.133→0.053 | 0.67 | -0.413% | ✅ | $+14.1487 |
| 8 | 2026-03-01 | 10 | UP | 0.408 | 0.494 | 0.144→0.058 | 0.77 | +0.520% | ✅ | $+15.7440 |

### Direction Breakdown

| Dir | Trades | Wins | Win% | PnL |
|-----|--------|------|------|-----|
| UP | 5 | 4 | 80.0% | $+42.74 |
| DOWN | 3 | 3 | 100.0% | $+39.52 |

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
