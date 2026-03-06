"""Tests for ShadowLogger and shadow mode integration."""
import csv
import os
import time
import pytest
from unittest.mock import patch

from src.execution.shadow_logger import ShadowLogger, TAKE_PROFIT_THRESHOLD, STOP_LOSS_PCT
from src.strategies.lag_arbitrage import LagArbitrageStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal_info(
    symbol="BTC", token_id="btc_up", direction="up",
    filter_reason="low_confidence", binance_move_pct=0.005,
    confidence=0.60, fair_value=0.56, edge=0.06, poly_price=0.50,
):
    return {
        "symbol": symbol, "token_id": token_id, "direction": direction,
        "filter_reason": filter_reason, "binance_move_pct": binance_move_pct,
        "confidence": confidence, "fair_value": fair_value, "edge": edge,
        "poly_price": poly_price, "timestamp": time.time(),
    }


@pytest.fixture
def shadow_logger(tmp_path):
    return ShadowLogger(csv_path=str(tmp_path / "shadow_trades.csv"))


def _read_csv(logger: ShadowLogger) -> list[dict]:
    with open(logger._csv_path) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# ShadowLogger core
# ---------------------------------------------------------------------------

class TestShadowLoggerCreation:
    def test_creates_csv_with_header(self, shadow_logger):
        assert os.path.exists(shadow_logger._csv_path)
        rows = _read_csv(shadow_logger)
        assert rows == []  # header only, no data rows

    def test_log_rejected_signal_returns_shadow_position(self, shadow_logger):
        pos = shadow_logger.log_rejected_signal(_signal_info())
        assert pos.shadow_id.startswith("SHADOW-")
        assert pos.symbol == "BTC"
        assert pos.direction == "up"
        assert pos.filter_reason == "low_confidence"
        assert pos.entry_price == 0.50
        assert not pos.closed

    def test_open_count_increments(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info())
        shadow_logger.log_rejected_signal(_signal_info(token_id="eth_up", symbol="ETH"))
        assert shadow_logger.open_count == 2


class TestShadowExitLogic:
    def test_take_profit_on_high_price(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.50))
        shadow_logger.update_price("btc_up", TAKE_PROFIT_THRESHOLD)

        rows = _read_csv(shadow_logger)
        assert len(rows) == 1
        assert rows[0]["exit_reason"] == "take_profit"
        assert float(rows[0]["exit_price"]) == TAKE_PROFIT_THRESHOLD
        assert shadow_logger.open_count == 0

    def test_stop_loss_on_price_drop(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.50))
        # -21% from 0.50 → clearly past the -20% stop threshold
        stop_price = 0.50 * (1 + STOP_LOSS_PCT) - 0.005
        shadow_logger.update_price("btc_up", stop_price)

        rows = _read_csv(shadow_logger)
        assert len(rows) == 1
        assert rows[0]["exit_reason"] == "stop_loss"

    def test_mid_range_price_does_not_close(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.50))
        shadow_logger.update_price("btc_up", 0.60)  # moved but not enough

        rows = _read_csv(shadow_logger)
        assert len(rows) == 0
        assert shadow_logger.open_count == 1

    def test_pnl_pct_computed_correctly(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.50))
        shadow_logger.update_price("btc_up", TAKE_PROFIT_THRESHOLD)

        rows = _read_csv(shadow_logger)
        expected_pnl = (TAKE_PROFIT_THRESHOLD - 0.50) / 0.50
        assert abs(float(rows[0]["pnl_pct"]) - expected_pnl) < 1e-6

    def test_update_only_affects_matching_token(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.50))
        shadow_logger.log_rejected_signal(_signal_info(token_id="eth_up", symbol="ETH", poly_price=0.50))

        shadow_logger.update_price("btc_up", TAKE_PROFIT_THRESHOLD)

        assert shadow_logger.open_count == 1
        open_pos = [p for p in shadow_logger._positions if not p.closed]
        assert open_pos[0].token_id == "eth_up"

    def test_multiple_positions_same_token(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.50))
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.52))
        shadow_logger.update_price("btc_up", TAKE_PROFIT_THRESHOLD)

        rows = _read_csv(shadow_logger)
        assert len(rows) == 2  # both closed


class TestShadowExpiry:
    def test_expire_all_closes_open_positions(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up"))
        shadow_logger.log_rejected_signal(_signal_info(token_id="eth_up"))
        assert shadow_logger.open_count == 2

        shadow_logger.expire_all()

        assert shadow_logger.open_count == 0
        rows = _read_csv(shadow_logger)
        assert all(r["exit_reason"] == "expired" for r in rows)

    def test_expire_does_not_double_close(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up", poly_price=0.50))
        shadow_logger.update_price("btc_up", TAKE_PROFIT_THRESHOLD)
        shadow_logger.expire_all()  # already closed, should be a no-op

        rows = _read_csv(shadow_logger)
        assert len(rows) == 1
        assert rows[0]["exit_reason"] == "take_profit"


class TestCSVContent:
    def test_all_expected_columns_present(self, shadow_logger):
        shadow_logger.log_rejected_signal(_signal_info(token_id="btc_up"))
        shadow_logger.update_price("btc_up", TAKE_PROFIT_THRESHOLD)

        rows = _read_csv(shadow_logger)
        assert len(rows) == 1
        for col in ["shadow_id", "symbol", "token_id", "direction", "filter_reason",
                    "signal_ts", "binance_move_pct", "confidence", "fair_value",
                    "edge", "entry_price", "exit_price", "exit_time", "exit_reason", "pnl_pct"]:
            assert col in rows[0]

    def test_optional_fields_empty_when_none(self, shadow_logger):
        info = _signal_info(token_id="btc_up")
        info["confidence"] = None
        info["fair_value"] = None
        info["edge"] = None
        shadow_logger.log_rejected_signal(info)
        shadow_logger.update_price("btc_up", TAKE_PROFIT_THRESHOLD)

        rows = _read_csv(shadow_logger)
        assert rows[0]["confidence"] == ""
        assert rows[0]["fair_value"] == ""
        assert rows[0]["edge"] == ""


# ---------------------------------------------------------------------------
# Strategy integration — last_shadow populated on rejection
# ---------------------------------------------------------------------------

TOKEN_IDS = {
    "BTC": {"up": "btc_up", "down": "btc_down"},
    "ETH": {"up": "eth_up", "down": "eth_down"},
}


@pytest.fixture
def strategy():
    return LagArbitrageStrategy(
        threshold_pct=0.003,
        lookback_secs=60,
        min_confidence=0.9,  # high threshold so confidence gate fires
        token_ids=TOKEN_IDS,
    )


class TestStrategyLastShadow:
    def test_last_shadow_none_before_evaluate(self, strategy):
        assert strategy.last_shadow is None

    def test_last_shadow_none_for_early_gates(self, strategy):
        # Gate 1 (no data)
        strategy.evaluate("BTC", None, {})
        assert strategy.last_shadow is None

        # Gate 2 (below threshold)
        strategy.evaluate("BTC", 0.001, {})
        assert strategy.last_shadow is None

    def test_last_shadow_populated_on_confidence_rejection(self, strategy):
        # Move passes threshold but confidence < 0.9 (the high min_confidence fixture)
        # threshold=0.003, move=0.004 → move_conf=0.44, edge_conf depends on edge
        strategy.evaluate("BTC", 0.004, {"btc_up": 0.44})
        assert strategy.last_shadow is not None
        assert strategy.last_shadow["filter_reason"] == "low_confidence"
        assert strategy.last_shadow["symbol"] == "BTC"
        assert strategy.last_shadow["token_id"] == "btc_up"
        assert strategy.last_shadow["confidence"] is not None
        assert strategy.last_shadow["fair_value"] is not None
        assert strategy.last_shadow["edge"] is not None

    def test_last_shadow_populated_on_no_edge(self, strategy):
        # Poly price already at fair value → edge <= 0
        # threshold=0.003, move=0.003 → fair_value=0.5+0.003*10=0.53
        # poly_price=0.55 → edge=-0.02
        strategy.evaluate("BTC", 0.003, {"btc_up": 0.55})
        assert strategy.last_shadow is not None
        assert strategy.last_shadow["filter_reason"] == "no_edge"
        assert strategy.last_shadow["confidence"] is None  # not computed
        assert strategy.last_shadow["edge"] is not None
        assert strategy.last_shadow["edge"] <= 0

    def test_last_shadow_populated_on_entry_price_range(self):
        # Use strategy with default ENTRY_PRICE_MIN/MAX (0.42-0.58)
        # Price outside [0.42, 0.58] → gate 6
        strat = LagArbitrageStrategy(
            threshold_pct=0.003, min_confidence=0.5, token_ids=TOKEN_IDS
        )
        strat.evaluate("BTC", 0.01, {"btc_up": 0.30})  # 0.30 < ENTRY_PRICE_MIN
        assert strat.last_shadow is not None
        assert strat.last_shadow["filter_reason"] == "entry_price_range"
        assert strat.last_shadow["confidence"] is None
        assert strat.last_shadow["fair_value"] is None

    def test_last_shadow_none_when_signal_passes(self, strategy):
        # Use low min_confidence so signal actually fires
        strat = LagArbitrageStrategy(
            threshold_pct=0.003, min_confidence=0.0, token_ids=TOKEN_IDS
        )
        sig = strat.evaluate("BTC", 0.01, {"btc_up": 0.45})
        assert sig is not None
        assert strat.last_shadow is None

    def test_last_shadow_reset_on_next_call(self, strategy):
        strategy.evaluate("BTC", 0.004, {"btc_up": 0.44})
        assert strategy.last_shadow is not None

        # Next call: early gate → shadow cleared
        strategy._signal_cooldown.clear()
        strategy.evaluate("BTC", 0.0001, {})  # below threshold
        assert strategy.last_shadow is None
