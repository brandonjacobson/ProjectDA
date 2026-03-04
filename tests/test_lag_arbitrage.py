"""Tests for LagArbitrageStrategy."""
import time
import pytest
from src.strategies.lag_arbitrage import LagArbitrageStrategy, TradeSignal

TOKEN_IDS = {
    "BTC": {"up": "btc_up", "down": "btc_down"},
    "ETH": {"up": "eth_up", "down": "eth_down"},
    "SOL": {"up": "sol_up", "down": "sol_down"},
}


@pytest.fixture
def strategy():
    return LagArbitrageStrategy(
        threshold_pct=0.003,
        lookback_secs=60,
        min_confidence=0.5,
        token_ids=TOKEN_IDS,
    )


class TestNoSignal:
    def test_returns_none_when_move_below_threshold(self, strategy):
        signal = strategy.evaluate("BTC", 0.001, {"btc_up": 0.45})
        assert signal is None

    def test_returns_none_when_binance_move_is_none(self, strategy):
        signal = strategy.evaluate("BTC", None, {"btc_up": 0.45})
        assert signal is None

    def test_returns_none_when_market_already_priced_in(self, strategy):
        # Binance moved +0.5%, poly price already at 0.55 (fair ~0.55 → edge ≤ 0)
        signal = strategy.evaluate("BTC", 0.005, {"btc_up": 0.60})
        assert signal is None

    def test_returns_none_for_unknown_symbol(self, strategy):
        signal = strategy.evaluate("XRP", 0.01, {})
        assert signal is None

    def test_returns_none_when_poly_price_missing(self, strategy):
        signal = strategy.evaluate("BTC", 0.01, {})
        assert signal is None


class TestSignalGeneration:
    def test_generates_up_signal_on_positive_move(self, strategy):
        signal = strategy.evaluate("BTC", 0.005, {"btc_up": 0.42})
        assert signal is not None
        assert signal.direction == "up"
        assert signal.symbol == "BTC"
        assert signal.token_id == "btc_up"

    def test_generates_down_signal_on_negative_move(self, strategy):
        signal = strategy.evaluate("BTC", -0.005, {"btc_down": 0.42})
        assert signal is not None
        assert signal.direction == "down"
        assert signal.token_id == "btc_down"

    def test_confidence_is_between_0_and_1(self, strategy):
        signal = strategy.evaluate("ETH", 0.01, {"eth_up": 0.35})
        assert signal is not None
        assert 0.0 <= signal.confidence <= 1.0

    def test_larger_move_gives_higher_confidence(self, strategy):
        sig_small = strategy.evaluate("BTC", 0.004, {"btc_up": 0.40})
        # Reset cooldown
        strategy._signal_cooldown.clear()
        sig_large = strategy.evaluate("BTC", 0.02, {"btc_up": 0.40})
        assert sig_small is not None
        assert sig_large is not None
        assert sig_large.confidence >= sig_small.confidence

    def test_signal_stores_binance_move(self, strategy):
        signal = strategy.evaluate("SOL", 0.008, {"sol_up": 0.38})
        assert signal is not None
        assert abs(signal.binance_move_pct - 0.008) < 1e-9

    def test_signal_stores_poly_price(self, strategy):
        signal = strategy.evaluate("SOL", 0.008, {"sol_up": 0.38})
        assert signal is not None
        assert signal.poly_price == 0.38


class TestCooldown:
    def test_no_double_signal_within_cooldown(self, strategy):
        sig1 = strategy.evaluate("BTC", 0.01, {"btc_up": 0.35})
        sig2 = strategy.evaluate("BTC", 0.01, {"btc_up": 0.35})
        assert sig1 is not None
        assert sig2 is None  # blocked by cooldown

    def test_different_symbols_not_blocked_by_each_other(self, strategy):
        sig_btc = strategy.evaluate("BTC", 0.01, {"btc_up": 0.35})
        sig_eth = strategy.evaluate("ETH", 0.01, {"eth_up": 0.35})
        assert sig_btc is not None
        assert sig_eth is not None

    def test_signal_allowed_after_cooldown_expires(self, strategy):
        strategy.COOLDOWN_SECS = 0  # instant cooldown for test
        sig1 = strategy.evaluate("BTC", 0.01, {"btc_up": 0.35})
        sig2 = strategy.evaluate("BTC", 0.01, {"btc_up": 0.35})
        assert sig1 is not None
        assert sig2 is not None


class TestTokenIdUpdate:
    def test_update_token_ids(self, strategy):
        new_ids = {"BTC": {"up": "new_btc_up", "down": "new_btc_down"}}
        strategy.update_token_ids(new_ids)
        signal = strategy.evaluate("BTC", 0.01, {"new_btc_up": 0.35})
        assert signal is not None
        assert signal.token_id == "new_btc_up"
