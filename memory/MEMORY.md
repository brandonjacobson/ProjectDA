# ProjectDA Memory

## Project Overview
Polymarket lag arbitrage trading bot. Paper mode default, --live flag for real trading.

## Key Files
- `main.py` — async orchestrator, `Bot` class
- `config/settings.py` — all config, loaded from `.env`
- `src/data/polymarket_feed.py` — Polymarket CLOB WebSocket
- `src/data/binance_feed.py` — Binance spot WebSocket, rolling price history
- `src/strategies/lag_arbitrage.py` — `LagArbitrageStrategy`, `TradeSignal`
- `src/execution/order_manager.py` — `OrderManager`, `Position`, `TradeRecord`
- `src/risk/risk_engine.py` — `RiskEngine` (kill switch, circuit breaker)
- `src/monitoring/alerts.py` — `AlertManager` (Telegram)
- `src/monitoring/dashboard.py` — `Dashboard` (Rich terminal)
- `tests/` — 41 pytest tests, all green

## Architecture
- Fully async (asyncio + websockets)
- Paper mode: trades logged to `trades/paper_trades.csv`
- Live mode: uses `py-clob-client` (needs POLY_* env vars)
- Market discovery: Gamma API at startup to resolve 15-min BTC/ETH/SOL token IDs

## Risk Parameters
- Max position: 2% portfolio per trade
- Daily loss cap: 5% → kill switch
- Max concurrent: 10
- Circuit breaker: 3 consecutive losses → 1hr pause

## Env Requirements
See `.env.example`. Never commit real credentials.

## Testing
```bash
python -m pytest tests/ -v
```
All 41 tests pass with no external deps needed (websockets/aiohttp not called in tests).

## Run
```bash
python main.py           # paper mode
python main.py --live    # live (real money)
```
