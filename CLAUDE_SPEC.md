# Polymarket Bot Specification

## Goal
Build a modular, production-grade Polymarket trading bot in Python that:
1. Connects to Polymarket's CLOB API via WebSocket for real-time data
2. Monitors BTC/ETH/SOL 15-minute up/down markets
3. Implements the lag arbitrage strategy (compare Binance spot vs Polymarket price)
4. Has a full risk management layer with kill switch and daily loss cap
5. Runs in paper trading mode by default (no real money until flag is set)
6. Sends Telegram alerts on errors, trades, and daily summaries
7. Logs everything to structured JSON logs

## Architecture
Build these modules in order:

### src/data/polymarket_feed.py
- WebSocket connection to wss://ws-live-data.polymarket.com
- Reconnect logic with exponential backoff
- Parse and emit order book events

### src/data/binance_feed.py
- WebSocket to Binance for BTC/ETH/SOL spot prices
- Real-time price streaming

### src/strategies/lag_arbitrage.py
- Compare Binance spot price momentum vs current Polymarket 15-min market price
- Signal: if Binance shows >0.3% move in last 60 seconds AND Polymarket hasn't adjusted, generate trade signal
- Confidence scoring 0-1

### src/execution/order_manager.py
- Paper trading mode (default): log trades to CSV, no real orders
- Live mode (flag): execute via py-clob-client
- Position tracking and P&L calculation

### src/risk/risk_engine.py
- Max position size: 2% of portfolio per trade
- Daily loss cap: 5% of portfolio → auto kill switch
- Max concurrent positions: 10
- Circuit breaker: pause 1 hour if 3 consecutive losses

### src/monitoring/alerts.py
- Telegram bot integration
- Alert on: trade execution, errors, daily P&L summary, kill switch triggered

### src/monitoring/dashboard.py
- Print live P&L, open positions, win rate to terminal every 60 seconds

### config/settings.py
- All configurable parameters in one place
- Environment variable loading

### main.py
- Orchestrates all modules
- Graceful shutdown handling
- Startup checks (API connectivity, wallet balance)

## Rules
- Paper trading mode is default. Require explicit --live flag to trade real money
- Never store private keys in code, only load from .env
- All errors should be caught, logged, and alerted — never crash silently
- Write pytest tests for all strategy logic
- Use async/await throughout for performance

## References
- py-clob-client docs: https://github.com/Polymarket/py-clob-client
- Polymarket CLOB API: https://docs.polymarket.com
- Open source reference: https://github.com/discountry/polymarket-trading-bot