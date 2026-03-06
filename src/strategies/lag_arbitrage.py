"""
Lag Arbitrage Strategy

Signal: if Binance shows >0.3% move in last 60s AND Polymarket price hasn't
adjusted, generate a trade signal with a confidence score 0-1.

Verbose status logging fires every STATUS_INTERVAL_SECS (default 60) showing
all symbols — even when no signal fires — so you can confirm the strategy is
actively evaluating and why each asset passed or failed.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from config.settings import ENTRY_PRICE_MIN, ENTRY_PRICE_MAX

logger = logging.getLogger(__name__)

# Polymarket YES token IDs for 15-min BTC/ETH/SOL up/down markets
# These are placeholder IDs; in production resolve via Gamma API
MARKET_TOKEN_IDS: dict[str, dict[str, str]] = {
    "BTC": {"up": "btc_15m_up_token", "down": "btc_15m_down_token"},
    "ETH": {"up": "eth_15m_up_token", "down": "eth_15m_down_token"},
    "SOL": {"up": "sol_15m_up_token", "down": "sol_15m_down_token"},
}

SYMBOLS_ORDER = ["BTC", "ETH", "SOL"]


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

    STATUS_INTERVAL_SECS: int = 60  # how often to emit the verbose status log

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

        # Per-symbol diagnostic state — updated on every evaluate() call
        self._diag: dict[str, dict] = {}
        self._last_status_time: dict[str, float] = {}  # symbol -> last log time

        # Shadow mode: populated when a meaningful signal is rejected (gates 6-8
        # or main.py filters). Reset to None at the start of each evaluate().
        self.last_shadow: Optional[dict] = None

    def evaluate(
        self,
        symbol: str,
        binance_move_pct: Optional[float],
        poly_prices: dict[str, float],  # token_id -> price
        binance_price: Optional[float] = None,  # raw spot price for logging
    ) -> Optional[TradeSignal]:
        """
        Evaluate conditions and return a TradeSignal if opportunity found.

        Args:
            symbol: "BTC", "ETH", or "SOL"
            binance_move_pct: % change in Binance price over lookback window
            poly_prices: mapping of token_id -> current Polymarket price
            binance_price: raw spot price (for status logging only)
        """
        self.last_shadow = None  # reset each call

        # --- Build diagnostic record for this symbol ---
        diag: dict = {
            "symbol": symbol,
            "ts": time.time(),
            "binance_price": binance_price,
            "binance_move_pct": binance_move_pct,
            "direction": None,
            "poly_up": None,
            "poly_down": None,
            "fair_value": None,
            "edge": None,
            "confidence": None,
            "result": None,   # "SIGNAL" | "FAIL:<reason>"
        }

        # Populate both poly prices for the status display regardless of direction
        up_id = self.token_ids.get(symbol, {}).get("up")
        down_id = self.token_ids.get(symbol, {}).get("down")
        if up_id:
            diag["poly_up"] = poly_prices.get(up_id)
        if down_id:
            diag["poly_down"] = poly_prices.get(down_id)

        def _finish(result: str) -> None:
            diag["result"] = result
            self._diag[symbol] = diag
            self._maybe_log_status(symbol)

        # --- Gate 1: Binance data available ---
        if binance_move_pct is None:
            _finish("FAIL: no_binance_data")
            return None

        # --- Gate 2: Momentum threshold ---
        if abs(binance_move_pct) < self.threshold_pct:
            _finish(
                f"FAIL: momentum {binance_move_pct:+.3%} below threshold ±{self.threshold_pct:.3%}"
            )
            return None

        # --- Gate 3: Cooldown ---
        last = self._signal_cooldown.get(symbol, 0)
        cooldown_remaining = self.COOLDOWN_SECS - (time.time() - last)
        if cooldown_remaining > 0:
            _finish(f"FAIL: cooldown {int(cooldown_remaining)}s remaining")
            return None

        # --- Gate 4: Token ID exists ---
        direction = "up" if binance_move_pct > 0 else "down"
        diag["direction"] = direction
        token_id = self.token_ids.get(symbol, {}).get(direction)
        if not token_id:
            _finish(f"FAIL: no token_id for {symbol}/{direction}")
            return None

        # --- Gate 5: Polymarket price available ---
        poly_price = poly_prices.get(token_id)
        if poly_price is None:
            _finish(f"FAIL: no poly price for token {token_id[:16]}…")
            return None

        # --- Gate 6: Entry price safe range ---
        if not (ENTRY_PRICE_MIN <= poly_price <= ENTRY_PRICE_MAX):
            _finish(
                f"FAIL: poly_price {poly_price:.3f} outside safe range "
                f"[{ENTRY_PRICE_MIN},{ENTRY_PRICE_MAX}]"
            )
            self.last_shadow = {
                "symbol": symbol, "token_id": token_id, "direction": direction,
                "filter_reason": "entry_price_range",
                "binance_move_pct": binance_move_pct,
                "confidence": None, "fair_value": None, "edge": None,
                "poly_price": poly_price, "timestamp": diag["ts"],
            }
            return None

        # --- Gate 7: Edge calculation ---
        scaling = 10
        fair_value = 0.5 + abs(binance_move_pct) * scaling
        fair_value = min(fair_value, 0.95)
        edge = fair_value - poly_price
        diag["fair_value"] = fair_value
        diag["edge"] = edge

        if edge <= 0:
            _finish(f"FAIL: no edge (fair={fair_value:.3f} poly={poly_price:.3f} edge={edge:+.3f})")
            self.last_shadow = {
                "symbol": symbol, "token_id": token_id, "direction": direction,
                "filter_reason": "no_edge",
                "binance_move_pct": binance_move_pct,
                "confidence": None, "fair_value": fair_value, "edge": edge,
                "poly_price": poly_price, "timestamp": diag["ts"],
            }
            return None

        # --- Gate 8: Confidence ---
        move_conf = min(abs(binance_move_pct) / (self.threshold_pct * 3), 1.0)
        edge_conf = min(edge / 0.15, 1.0)
        confidence = 0.5 * move_conf + 0.5 * edge_conf
        diag["confidence"] = confidence

        if confidence < self.min_confidence:
            _finish(f"FAIL: confidence {confidence:.2f} < min {self.min_confidence:.2f}")
            self.last_shadow = {
                "symbol": symbol, "token_id": token_id, "direction": direction,
                "filter_reason": "low_confidence",
                "binance_move_pct": binance_move_pct,
                "confidence": confidence, "fair_value": fair_value, "edge": edge,
                "poly_price": poly_price, "timestamp": diag["ts"],
            }
            return None

        # --- All gates passed → SIGNAL ---
        _finish("SIGNAL")

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

    # ------------------------------------------------------------------
    # Periodic verbose status logging
    # ------------------------------------------------------------------

    def _maybe_log_status(self, symbol: str) -> None:
        """Emit per-symbol diagnostic block at most once per STATUS_INTERVAL_SECS."""
        now = time.time()
        if now - self._last_status_time.get(symbol, 0.0) < self.STATUS_INTERVAL_SECS:
            return
        if symbol not in self._diag:
            return
        self._last_status_time[symbol] = now
        self._log_status(symbol)

    def _log_status(self, symbol: str) -> None:
        """Format and emit the diagnostic block for a single symbol."""
        d = self._diag.get(symbol)
        if d is None:
            return

        ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        sep = "─" * 72

        lines = [
            "",
            sep,
            f"  LAG ARBIT DIAGNOSTIC  {symbol}  {ts}",
            f"  Threshold: ±{self.threshold_pct:.3%}  "
            f"Lookback: {self.lookback_secs}s  "
            f"Min confidence: {self.min_confidence:.2f}  "
            f"Cooldown: {self.COOLDOWN_SECS}s",
            sep,
        ]

        # Line 1: Binance price + momentum
        spot = d["binance_price"]
        move = d["binance_move_pct"]
        spot_str = f"${spot:>10,.2f}" if spot is not None else "         N/A"
        move_str = f"{move:>+8.3%}" if move is not None else "      N/A"
        thresh_arrow = (
            "✓ PASS" if move is not None and abs(move) >= self.threshold_pct
            else "✗ FAIL"
        )
        lines.append(
            f"  {symbol:<4}  spot={spot_str}  "
            f"momentum={move_str} (60s)  threshold={thresh_arrow}"
        )

        # Line 2: Polymarket prices
        up_p = d["poly_up"]
        dn_p = d["poly_down"]
        up_str = f"{up_p:.3f}" if up_p is not None else "  N/A"
        dn_str = f"{dn_p:.3f}" if dn_p is not None else "  N/A"
        lines.append(f"        poly UP={up_str}  poly DOWN={dn_str}")

        # Line 3: Edge / confidence (only when we got that far)
        fv        = d["fair_value"]
        edge      = d["edge"]
        conf      = d["confidence"]
        direction = d["direction"]
        if fv is not None:
            dir_str  = direction.upper() if direction else "?"
            conf_str = f"{conf:.2f}" if conf is not None else " N/A"
            lines.append(
                f"        direction={dir_str}  "
                f"fair={fv:.3f}  edge={edge:+.3f}  conf={conf_str}"
            )

        # Line 4: Overall result
        result = d.get("result", "pending")
        marker = "🟢 SIGNAL FIRED" if result == "SIGNAL" else f"🔴 {result}"
        lines.append(f"        → {marker}")
        lines.append(sep)

        logger.info("\n".join(lines))

    def update_token_ids(self, token_ids: dict[str, dict[str, str]]) -> None:
        """Update market token IDs (called after market discovery)."""
        self.token_ids = token_ids
        logger.info(f"Token IDs updated: {list(token_ids.keys())}")
