"""
Synthetic Polymarket binary market price model.

Models the YES price of a "Will BTC be higher in 15 minutes?" market
using a binary option approach (normal CDF on current return / remaining vol).

Key insight for lag arbitrage backtesting:
- `fair_price`  = what the market SHOULD price right now (Binance-informed)
- `lagged_price` = what the market ACTUALLY shows (Binance price from lag_secs ago)
- Edge = fair_price - lagged_price (what we capture by buying at lagged_price)
"""
import math
from scipy.stats import norm


class BinaryMarketModel:
    """
    Prices a "BTC UP in T minutes" binary market.

    Parameters
    ----------
    window_secs : int
        Total market duration (default 900 = 15 minutes)
    daily_vol : float
        Estimated daily price volatility (e.g. 0.025 = 2.5%)
    lag_secs : int
        Simulated Polymarket price lag behind Binance (default 60s)
    """

    def __init__(
        self,
        window_secs: int = 900,
        daily_vol: float = 0.025,
        lag_secs: int = 60,
    ):
        self.window_secs = window_secs
        self.daily_vol = daily_vol
        self.lag_secs = lag_secs
        # Per-second vol
        self._vol_per_sec = daily_vol / math.sqrt(86400)

    def fair_price(self, current_return: float, elapsed_secs: float) -> float:
        """
        Fair YES probability given current return and elapsed time.

        At expiry (elapsed_secs >= window_secs):
            returns 1.0 if current_return > 0 else 0.0

        During the window:
            P(YES) = N(current_return / sigma_remaining)
            where sigma_remaining = vol_per_sec * sqrt(remaining_secs)
        """
        remaining = max(self.window_secs - elapsed_secs, 0.0)
        if remaining == 0:
            return 1.0 if current_return > 0 else 0.0

        sigma_remaining = self._vol_per_sec * math.sqrt(remaining)
        if sigma_remaining <= 0:
            return 0.5

        d = current_return / sigma_remaining
        # Clip to [0.02, 0.98] — real markets never trade at the extremes
        return float(max(0.02, min(0.98, norm.cdf(d))))

    def lagged_price(self, returns_series: list[tuple[float, float]], query_time: float) -> float:
        """
        Return the Polymarket YES price at `query_time` using a return
        from `lag_secs` ago (simulating market price lag).

        Args:
            returns_series: list of (elapsed_secs, cumulative_return) tuples
            query_time: elapsed seconds at which we want the lagged price
        """
        lag_time = max(query_time - self.lag_secs, 0.0)
        # Find the return at lag_time
        lagged_return = 0.0
        for (t, r) in reversed(returns_series):
            if t <= lag_time:
                lagged_return = r
                break
        return self.fair_price(lagged_return, lag_time)

    def simulate_window(
        self,
        closes_1m: list[float],
    ) -> list[dict]:
        """
        Simulate a single 15-min market window from 1-minute closes.

        Args:
            closes_1m: list of minute close prices (index 0 = window open)
                       must have >= 2 elements, ideal >= 15

        Returns:
            list of dicts per minute bar:
                {
                  'minute': int (0-14),
                  'elapsed_secs': float,
                  'close': float,
                  'cum_return': float,
                  'fair_price': float,
                  'lagged_price': float,
                  'resolved': bool (True at last bar),
                  'resolution': float (1.0 or 0.0, only at last bar),
                }
        """
        if len(closes_1m) < 2:
            return []

        open_price = closes_1m[0]
        bars = []
        returns_series = []

        for i, close in enumerate(closes_1m):
            elapsed = i * 60.0
            cum_ret = (close - open_price) / open_price if open_price else 0.0
            returns_series.append((elapsed, cum_ret))

            fp = self.fair_price(cum_ret, elapsed)
            lp = self.lagged_price(returns_series, elapsed)
            is_last = (i == len(closes_1m) - 1)

            bar = {
                "minute": i,
                "elapsed_secs": elapsed,
                "close": close,
                "cum_return": cum_ret,
                "fair_price": fp,
                "lagged_price": lp,
                "resolved": is_last,
                "resolution": (1.0 if cum_ret > 0 else 0.0) if is_last else None,
            }
            bars.append(bar)

        return bars
