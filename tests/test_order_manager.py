"""Tests for OrderManager."""
import asyncio
import os
import pytest
import pytest_asyncio
from src.execution.order_manager import OrderManager, Position


@pytest.fixture
def om(tmp_path):
    return OrderManager(
        paper_mode=True,
        trades_dir=str(tmp_path),
        portfolio_size=1000.0,
    )


class TestPlaceOrder:
    def test_place_creates_position(self, om):
        record = asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.45, 0.8))
        assert record is not None
        assert "tok1" in om.positions
        assert om.positions["tok1"].entry_price == 0.45

    def test_no_duplicate_position(self, om):
        asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.45))
        record2 = asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.45))
        assert record2 is None
        assert len(om.positions) == 1

    def test_trade_logged_to_csv(self, om):
        asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.45))
        csv_path = os.path.join(om.trades_dir, "paper_trades.csv")
        with open(csv_path) as f:
            lines = f.readlines()
        assert len(lines) == 2  # header + 1 trade


class TestClosePosition:
    def test_close_removes_from_open(self, om):
        asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.45))
        asyncio.run(om.close_position("tok1", 0.80, "take_profit"))
        assert "tok1" not in om.positions
        assert len(om.closed_positions) == 1

    def test_close_calculates_pnl(self, om):
        asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.50))
        asyncio.run(om.close_position("tok1", 0.75, "tp"))
        pos = om.closed_positions[0]
        # 20/0.50 = 40 shares * (0.75 - 0.50) = 10.0
        assert abs(pos.pnl - 10.0) < 0.01

    def test_close_nonexistent_returns_none(self, om):
        result = asyncio.run(om.close_position("nonexistent", 0.5))
        assert result is None


class TestPnL:
    def test_total_pnl_includes_closed(self, om):
        asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.50))
        asyncio.run(om.close_position("tok1", 0.75, "tp"))
        assert om.total_pnl > 0

    def test_win_rate_correct(self, om):
        asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.50))
        asyncio.run(om.close_position("tok1", 0.75, "win"))
        asyncio.run(om.place_order("tok2", "ETH", "down", 20.0, 0.50))
        asyncio.run(om.close_position("tok2", 0.25, "loss"))
        assert om.win_rate == 0.5

    def test_update_price_updates_position(self, om):
        asyncio.run(om.place_order("tok1", "BTC", "up", 20.0, 0.50))
        om.update_price("tok1", 0.65)
        assert om.positions["tok1"].current_price == 0.65
