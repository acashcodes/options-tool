"""Tests for implied volatility solver."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from greeks import bs_price
from iv_solver import implied_vol_from_price


class TestIVSolver:
    def test_round_trip_call(self):
        """Generate a known BSM price from sigma=0.25, solve and verify."""
        S, K, t, r, q = 100, 100, 30 / 365, 0.05, 0.0
        sigma_true = 0.25
        market_price = bs_price(S, K, t, r, sigma_true, "call", q=q)

        solved = implied_vol_from_price(
            market_price=market_price, S=S, K=K, t=t, r=r, q=q,
            option_type="call",
        )
        assert solved is not None
        assert solved == pytest.approx(sigma_true, abs=1e-4)

    def test_round_trip_put(self):
        S, K, t, r, q = 150, 145, 60 / 365, 0.04, 0.01
        sigma_true = 0.30
        market_price = bs_price(S, K, t, r, sigma_true, "put", q=q)

        solved = implied_vol_from_price(
            market_price=market_price, S=S, K=K, t=t, r=r, q=q,
            option_type="put",
        )
        assert solved is not None
        assert solved == pytest.approx(sigma_true, abs=1e-4)

    def test_round_trip_with_dividend(self):
        S, K, t, r, q = 200, 210, 90 / 365, 0.045, 0.02
        sigma_true = 0.28
        market_price = bs_price(S, K, t, r, sigma_true, "call", q=q)

        solved = implied_vol_from_price(
            market_price=market_price, S=S, K=K, t=t, r=r, q=q,
            option_type="call",
        )
        assert solved is not None
        assert solved == pytest.approx(sigma_true, abs=1e-4)

    def test_no_bracket_returns_none(self):
        """Impossible market price should return None."""
        # A call can't be worth more than S
        solved = implied_vol_from_price(
            market_price=999, S=100, K=100, t=30 / 365, r=0.05, q=0.0,
            option_type="call",
        )
        assert solved is None

    def test_zero_price_returns_none(self):
        solved = implied_vol_from_price(
            market_price=0, S=100, K=100, t=30 / 365, r=0.05, q=0.0,
            option_type="call",
        )
        assert solved is None

    def test_negative_time_returns_none(self):
        solved = implied_vol_from_price(
            market_price=5, S=100, K=100, t=-1, r=0.05, q=0.0,
            option_type="call",
        )
        assert solved is None
