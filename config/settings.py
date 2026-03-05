"""Centralised configuration — all params loaded from .env or defaults."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Mode ---
PAPER_MODE: bool = os.getenv("PAPER_MODE", "true").lower() == "true"

# --- Polymarket CLOB ---
POLY_HOST: str = os.getenv("POLY_HOST", "https://clob.polymarket.com")
POLY_CHAIN_ID: int = int(os.getenv("POLY_CHAIN_ID", "137"))
POLY_PRIVATE_KEY: str = os.getenv("POLY_PRIVATE_KEY", "")
POLY_API_KEY: str = os.getenv("POLY_API_KEY", "")
POLY_API_SECRET: str = os.getenv("POLY_API_SECRET", "")
POLY_API_PASSPHRASE: str = os.getenv("POLY_API_PASSPHRASE", "")

# --- WebSocket endpoints ---
POLY_WS_URL: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
BINANCE_WS_URL: str = "wss://stream.binance.us:9443/ws"  # individual stream base

# --- Markets to monitor ---
SYMBOLS: list[str] = ["BTC", "ETH", "SOL"]

# --- Strategy ---
LAG_THRESHOLD_PCT: float = float(os.getenv("LAG_THRESHOLD_PCT", "0.001"))  # 0.1% (lowered for pipeline testing)
LAG_LOOKBACK_SECS: int = int(os.getenv("LAG_LOOKBACK_SECS", "60"))
MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.64"))
# Entry price safe range — reject signals outside this band (too close to 0 or 1 = illiquid extremes)
ENTRY_PRICE_MIN: float = float(os.getenv("ENTRY_PRICE_MIN", "0.42"))
ENTRY_PRICE_MAX: float = float(os.getenv("ENTRY_PRICE_MAX", "0.58"))

# --- Risk ---
PORTFOLIO_SIZE: float = float(os.getenv("PORTFOLIO_SIZE", "1000.0"))
MAX_POSITION_PCT: float = float(os.getenv("MAX_POSITION_PCT", "0.02"))
DAILY_LOSS_CAP_PCT: float = float(os.getenv("DAILY_LOSS_CAP_PCT", "0.05"))
MAX_CONCURRENT_POSITIONS: int = int(os.getenv("MAX_CONCURRENT_POSITIONS", "10"))
CIRCUIT_BREAKER_LOSSES: int = int(os.getenv("CIRCUIT_BREAKER_LOSSES", "3"))
CIRCUIT_BREAKER_PAUSE_SECS: int = int(os.getenv("CIRCUIT_BREAKER_PAUSE_SECS", "3600"))

# --- Telegram ---
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
ALERTS_ENABLED: bool = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# --- Logging ---
LOG_DIR: str = os.getenv("LOG_DIR", "logs")
TRADES_DIR: str = os.getenv("TRADES_DIR", "trades")

# --- Dashboard ---
DASHBOARD_REFRESH_SECS: int = int(os.getenv("DASHBOARD_REFRESH_SECS", "60"))
