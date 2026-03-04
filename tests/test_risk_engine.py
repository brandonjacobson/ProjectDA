"""Tests for RiskEngine."""
import time
import pytest
from src.risk.risk_engine import RiskEngine


@pytest.fixture
def risk():
    return RiskEngine(
        portfolio_size=1000.0,
        max_position_pct=0.02,
        daily_loss_cap_pct=0.05,
        max_concurrent=3,
        circuit_breaker_losses=2,
        circuit_breaker_pause_secs=1,  # short for tests
    )


class TestCheckTrade:
    def test_allows_normal_trade(self, risk):
        allowed, reason = risk.check_trade(0, 0.0, 10.0)
        assert allowed is True

    def test_blocks_when_max_positions_reached(self, risk):
        allowed, reason = risk.check_trade(3, 0.0, 10.0)
        assert allowed is False
        assert "concurrent" in reason.lower()

    def test_blocks_when_daily_loss_cap_hit(self, risk):
        allowed, reason = risk.check_trade(0, -60.0, 10.0)
        assert allowed is False

    def test_blocks_when_size_exceeds_max(self, risk):
        allowed, reason = risk.check_trade(0, 0.0, 100.0)
        assert allowed is False
        assert "size" in reason.lower()

    def test_triggers_kill_switch_on_loss_cap(self, risk):
        risk.check_trade(0, -60.0, 10.0)
        assert risk.kill_switch_active is True

    def test_blocks_when_kill_switch_active(self, risk):
        risk.trigger_kill_switch("test")
        allowed, reason = risk.check_trade(0, 0.0, 10.0)
        assert allowed is False
        assert "kill switch" in reason.lower()


class TestPositionSize:
    def test_max_size_is_correct(self, risk):
        assert risk.max_position_size == 20.0  # 2% of 1000

    def test_size_scales_with_confidence(self, risk):
        full = risk.calculate_position_size(1.0)
        half = risk.calculate_position_size(0.5)
        assert full == 20.0
        assert half == 10.0

    def test_size_caps_at_1(self, risk):
        size = risk.calculate_position_size(999.0)
        assert size == 20.0


class TestCircuitBreaker:
    def test_triggers_after_consecutive_losses(self, risk):
        risk.record_trade_result(-1.0)
        risk.record_trade_result(-1.0)
        assert risk.is_circuit_breaker_active() is True

    def test_resets_consecutive_on_win(self, risk):
        risk.record_trade_result(-1.0)
        risk.record_trade_result(5.0)
        assert risk.consecutive_losses == 0

    def test_circuit_breaker_expires(self, risk):
        risk.record_trade_result(-1.0)
        risk.record_trade_result(-1.0)
        assert risk.is_circuit_breaker_active() is True
        time.sleep(1.1)
        assert risk.is_circuit_breaker_active() is False

    def test_circuit_breaker_blocks_trades(self, risk):
        risk.record_trade_result(-1.0)
        risk.record_trade_result(-1.0)
        allowed, reason = risk.check_trade(0, 0.0, 10.0)
        assert allowed is False
        assert "circuit" in reason.lower()


class TestKillSwitch:
    def test_manual_kill_switch(self, risk):
        risk.trigger_kill_switch("manual test")
        assert risk.kill_switch_active is True
        assert risk.kill_reason == "manual test"

    def test_reset_kill_switch(self, risk):
        risk.trigger_kill_switch("test")
        risk.reset_kill_switch()
        assert risk.kill_switch_active is False

    def test_callback_fired_on_kill(self, risk):
        called = []
        risk.on_kill_switch(lambda r: called.append(r))
        risk.trigger_kill_switch("cb test")
        assert len(called) == 1
        assert called[0] == "cb test"

    def test_kill_switch_only_fires_once(self, risk):
        called = []
        risk.on_kill_switch(lambda r: called.append(r))
        risk.trigger_kill_switch("first")
        risk.trigger_kill_switch("second")
        assert len(called) == 1
