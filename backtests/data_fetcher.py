"""
Backtest data fetcher.

- Binance.US REST API: 1-minute OHLCV klines for BTC/ETH/SOL
- Gamma API: resolved Polymarket markets for metadata (best-effort)
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BINANCE_US_BASE = "https://api.binance.us/api/v3"
GAMMA_BASE = "https://gamma-api.polymarket.com"


def fetch_binance_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    days_back: int = 30,
) -> pd.DataFrame:
    """
    Fetch 1-minute Binance.US klines.

    Returns DataFrame with columns:
        open_time (datetime, UTC), open, high, low, close, volume
    """
    if end_dt is None:
        end_dt = datetime.now(timezone.utc)
    if start_dt is None:
        start_dt = datetime(end_dt.year, end_dt.month, end_dt.day, tzinfo=timezone.utc)
        # go back `days_back` days
        import datetime as dt_mod
        start_dt = end_dt - dt_mod.timedelta(days=days_back)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    all_rows = []
    limit = 1000  # Binance.US max per request
    cursor = start_ms

    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": limit,
        }
        try:
            resp = requests.get(f"{BINANCE_US_BASE}/klines", params=params, timeout=15)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            logger.error(f"Binance.US klines error: {e}")
            break

        if not rows:
            break

        all_rows.extend(rows)
        last_ts = rows[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 60_000  # advance by 1 minute

        if len(rows) < limit:
            break  # got everything

        time.sleep(0.2)  # rate-limit courtesy

    if not all_rows:
        logger.warning(f"No klines fetched for {symbol}")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = df.sort_values("open_time").reset_index(drop=True)

    logger.info(f"Fetched {len(df)} {symbol} {interval} candles from Binance.US "
                f"({df['open_time'].iloc[0].date()} → {df['open_time'].iloc[-1].date()})")
    return df[["open_time", "open", "high", "low", "close", "volume"]]


def estimate_daily_volatility(df_1m: pd.DataFrame) -> float:
    """
    Estimate annualised daily volatility from 1-minute close returns.
    Returns daily vol (e.g. 0.025 = 2.5% per day).
    """
    if df_1m.empty or len(df_1m) < 60:
        return 0.02  # default 2%
    returns = df_1m["close"].pct_change().dropna()
    # 1-min vol → daily vol (1440 minutes/day)
    min_vol = returns.std()
    daily_vol = min_vol * (1440 ** 0.5)
    return float(daily_vol)


def fetch_gamma_btc_markets(limit: int = 500) -> list[dict]:
    """
    Best-effort fetch of resolved BTC markets from Gamma API.
    Returns list of market dicts (may be empty if API changes).
    """
    try:
        resp = requests.get(
            f"{GAMMA_BASE}/markets",
            params={"closed": "true", "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        markets = resp.json()
        btc = [
            m for m in markets
            if "btc" in m.get("question", "").lower()
            or "bitcoin" in m.get("question", "").lower()
        ]
        logger.info(f"Gamma API: {len(btc)} resolved BTC markets found (of {len(markets)} total)")
        return btc
    except Exception as e:
        logger.warning(f"Gamma API fetch failed: {e}")
        return []
