"""
Lag Arbitrage Strategy

Signal: if Binance shows >0.3% move in last 60s AND Polymarket price hasn't
adjusted, generate a trade signal with a confidence score 0-1.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Polymarket YES token IDs for 15-min BTC/ETH/SOL up/down markets
# These are placeholder IDs; in production resolve via Gamma API
MARKET_TOKEN_IDS: dict[str, dict[str, str]] = {
    "BTC": {"up": "btc_15m_up_token", "down": "btc_15m_down_token"},
    "ETH": {"up": "eth_15m_up_token", "down": "eth_15m_down_token"},
    "SOL": {"up": "sol_15m_up_token", "down": "sol_15m_down_token"},
}


@dataclass
class TradeSignal:
    symbol: str          # BTC / ETH / SOL
    direction: str       # "up" or "down"
    token_id: str        # Polymarket YES token ID
    binance_move_pct: float   # observed Binance % move
    poly_price: float         # current Polymarket YES price
    confidence: float         # 0-1
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        return (
            f"TradeSignal({self.symbol} {self.direction.upper()} | "
            f"binance={self.binance_move_pct:+.3%} poly={self.poly_price:.3f} "
            f"conf={self.confidence:.2f})"
        )


class LagArbitrageStrategy:
    """
    Detects lag between Binance spot momentum and Polymarket 15-min market pricing.

    Logic:
    - If Binance has moved > threshold % in last `lookback_secs`:
      - If move is positive → look at UP market's YES price
        - If YES price < 0.5 + expected_edge → signal to BUY YES (underpriced)
      - If move is negative → look at DOWN market's YES price
        - If YES price < 0.5 + expected_edge → signal to BUY YES (underpriced)
    - Confidence = f(magnitude of Binance move, poly_price_edge)
    """

    def __init__(
        self,
        threshold_pct: float = 0.003,
        lookback_secs: int = 60,
        min_confidence: float = 0.6,
        token_ids: Optional[dict] = None,
    ):
        self.threshold_pct = threshold_pct
        self.lookback_secs = lookback_secs
        self.min_confidence = min_confidence
        self.token_ids = token_ids or MARKET_TOKEN_IDS
        self._signal_cooldown: dict[str, float] = {}  # symbol -> last signal time
        self.COOLDOWN_SECS = 300  # don't re-signal same symbol within 5 min

    def evaluate(
        self,
        symbol: str,
        binance_move_pct: Optional[float],
        poly_prices: dict[str, float],  # token_id -> price
    ) -> Optional[TradeSignal]:
        """
        Evaluate conditions and return a TradeSignal if opportunity found.

        Args:
            symbol: "BTC", "ETH", or "SOL"
            binance_move_pct: % change in Binance price over lookback window
            poly_prices: mapping of token_id -> current Polymarket price
        """
        if binance_move_pct is None:
            return None

        if abs(binance_move_pct) < self.threshold_pct:
            return None

        # Check cooldown
        last = self._signal_cooldown.get(symbol, 0)
        if time.time() - last < self.COOLDOWN_SECS:
            return None

        direction = "up" if binance_move_pct > 0 else "down"
        token_id = self.token_ids.get(symbol, {}).get(direction)
        if not token_id:
            return None

        poly_price = poly_prices.get(token_id)
        if poly_price is None:
            return None

        # Calculate expected fair value:
        # If Binance just moved +1% in 60s, a 15-min UP market SHOULD be > 0.5
        # Fair value estimate: naive 0.5 + move_pct * scaling_factor
        scaling = 10  # empirical: 1% binance move -> ~10% adjustment in 15m market
        fair_value = 0.5 + abs(binance_move_pct) * scaling
        fair_value = min(fair_value, 0.95)  # cap

        # Edge: how much does market underestimate the probability?
        edge = fair_value - poly_price
        if edge <= 0:
            # Market already priced in (or overpriced)
            return None

        # Confidence: blend of move magnitude and edge size
        move_conf = min(abs(binance_move_pct) / (self.threshold_pct * 3), 1.0)
        edge_conf = min(edge / 0.15, 1.0)  # full confidence if edge > 15%
        confidence = 0.5 * move_conf + 0.5 * edge_conf

        if confidence < self.min_confidence:
            return None

        signal = TradeSignal(
            symbol=symbol,
            direction=direction,
            token_id=token_id,
            binance_move_pct=binance_move_pct,
            poly_price=poly_price,
            confidence=confidence,
        )
        self._signal_cooldown[symbol] = time.time()
        logger.info(f"Signal generated: {signal}")
        return signal

    def update_token_ids(self, token_ids: dict[str, dict[str, str]]) -> None:
        """Update market token IDs (called after market discovery)."""
        self.token_ids = token_ids
        logger.info(f"Token IDs updated: {list(token_ids.keys())}")
