"""Pytest port of test_strategy_math.py.

Tests payoff formulas, breakevens, max profit/loss for all strategy types,
using the canonical strategy_engine.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from strategy_engine.models import StrategyLeg
from strategy_engine.payoff import payoff_at_expiration, strategy_payoff_at_expiration


def make_leg(opt_type, strike, premium, action, qty=1):
    """Create a StrategyLeg from the old dict-style test params."""
    return StrategyLeg(
        instrument="option",
        option_type="call" if opt_type == "Call" else "put",
        action=action,
        quantity=qty,
        strike=strike,
        entry_price=premium,
        expiration="2026-06-20",
        multiplier=100,
    )


def leg_pl(leg, stock_price):
    """Compute P&L for a single leg at expiry."""
    return payoff_at_expiration(leg, stock_price)


# ---------------------------------------------------------------------------
# leg_pl unit tests
# ---------------------------------------------------------------------------

class TestLegPL:
    def test_long_call_deep_itm(self):
        leg = make_leg("Call", 100, 5, "buy")
        assert leg_pl(leg, 150) == pytest.approx(4500, abs=1)

    def test_long_call_atm(self):
        leg = make_leg("Call", 100, 5, "buy")
        assert leg_pl(leg, 100) == pytest.approx(-500, abs=1)

    def test_long_call_otm(self):
        leg = make_leg("Call", 100, 5, "buy")
        assert leg_pl(leg, 50) == pytest.approx(-500, abs=1)

    def test_long_put_deep_itm(self):
        leg = make_leg("Put", 100, 4, "buy")
        assert leg_pl(leg, 50) == pytest.approx(4600, abs=1)

    def test_long_put_atm(self):
        leg = make_leg("Put", 100, 4, "buy")
        assert leg_pl(leg, 100) == pytest.approx(-400, abs=1)

    def test_short_call_otm(self):
        leg = make_leg("Call", 100, 5, "sell")
        assert leg_pl(leg, 90) == pytest.approx(500, abs=1)

    def test_short_call_deep_itm(self):
        leg = make_leg("Call", 100, 5, "sell")
        assert leg_pl(leg, 200) == pytest.approx(-9500, abs=1)

    def test_short_put_otm(self):
        leg = make_leg("Put", 100, 4, "sell")
        assert leg_pl(leg, 110) == pytest.approx(400, abs=1)

    def test_quantity_multiplier(self):
        leg = make_leg("Call", 100, 5, "buy", qty=3)
        assert leg_pl(leg, 120) == pytest.approx((20 - 5) * 100 * 3, abs=1)


# ---------------------------------------------------------------------------
# Strategy payoff formulas
# ---------------------------------------------------------------------------

class TestCallDebitSpread:
    def test_payoff_at_various_prices(self):
        K1, K2, prem1, prem2 = 100, 110, 6, 2
        net_debit = prem1 - prem2
        width = K2 - K1
        legs = [make_leg("Call", K1, prem1, "buy"), make_leg("Call", K2, prem2, "sell")]

        for St in [80, 100, 104, 107, 110, 120, 150]:
            spread_val = min(max(St - K1, 0), width)
            expected = (spread_val - net_debit) * 100
            actual = strategy_payoff_at_expiration(legs, St)
            assert actual == pytest.approx(expected, abs=1), f"Failed at St={St}"

    def test_breakeven_pl_zero(self):
        legs = [make_leg("Call", 100, 6, "buy"), make_leg("Call", 110, 2, "sell")]
        be = 104
        assert abs(strategy_payoff_at_expiration(legs, be)) < 1


class TestPutDebitSpread:
    def test_payoff(self):
        K1, K2, prem1, prem2 = 100, 90, 4, 1
        net_debit = prem1 - prem2
        width = K1 - K2
        legs = [make_leg("Put", K1, prem1, "buy"), make_leg("Put", K2, prem2, "sell")]

        for St in [50, 85, 90, 97, 100, 110]:
            spread_val = min(max(K1 - St, 0), width)
            expected = (spread_val - net_debit) * 100
            actual = strategy_payoff_at_expiration(legs, St)
            assert actual == pytest.approx(expected, abs=1), f"Failed at St={St}"


class TestCallCreditSpread:
    def test_payoff(self):
        K1, K2, prem1, prem2 = 105, 110, 3, 1
        net_credit = prem1 - prem2
        width = K2 - K1
        legs = [make_leg("Call", K1, prem1, "sell"), make_leg("Call", K2, prem2, "buy")]

        for St in [90, 105, 107, 108, 110, 120]:
            intrinsic_loss = max(St - K1, 0)
            actual_loss = min(intrinsic_loss, width)
            expected = (net_credit - actual_loss) * 100
            actual = strategy_payoff_at_expiration(legs, St)
            assert actual == pytest.approx(expected, abs=1), f"Failed at St={St}"


class TestIronCondor:
    def test_center_max_profit(self):
        legs = [
            make_leg("Put", 85, 0.50, "buy"),
            make_leg("Put", 90, 1.50, "sell"),
            make_leg("Call", 110, 1.50, "sell"),
            make_leg("Call", 115, 0.50, "buy"),
        ]
        assert strategy_payoff_at_expiration(legs, 100) == pytest.approx(200, abs=1)

    def test_below_wings_max_loss(self):
        legs = [
            make_leg("Put", 85, 0.50, "buy"),
            make_leg("Put", 90, 1.50, "sell"),
            make_leg("Call", 110, 1.50, "sell"),
            make_leg("Call", 115, 0.50, "buy"),
        ]
        assert strategy_payoff_at_expiration(legs, 80) == pytest.approx(-300, abs=1)

    def test_above_wings_max_loss(self):
        legs = [
            make_leg("Put", 85, 0.50, "buy"),
            make_leg("Put", 90, 1.50, "sell"),
            make_leg("Call", 110, 1.50, "sell"),
            make_leg("Call", 115, 0.50, "buy"),
        ]
        assert strategy_payoff_at_expiration(legs, 120) == pytest.approx(-300, abs=1)


class TestBreakevenAccuracy:
    @pytest.mark.parametrize("name,legs,be", [
        ("Long Call", [make_leg("Call", 100, 5, "buy")], 105),
        ("Long Put", [make_leg("Put", 100, 4, "buy")], 96),
        ("CDS", [make_leg("Call", 100, 6, "buy"), make_leg("Call", 110, 2, "sell")], 104),
        ("PDS", [make_leg("Put", 100, 4, "buy"), make_leg("Put", 90, 1, "sell")], 97),
        ("CCS", [make_leg("Call", 105, 3, "sell"), make_leg("Call", 110, 1, "buy")], 107),
        ("PCS", [make_leg("Put", 95, 3, "sell"), make_leg("Put", 90, 1, "buy")], 93),
    ])
    def test_pl_at_breakeven_is_zero(self, name, legs, be):
        pl = strategy_payoff_at_expiration(legs, be)
        assert abs(pl) < 1, f"{name} BE={be}: P&L={pl}"
