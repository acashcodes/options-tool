"""Tests for the strategy_engine: payoff, metrics, breakevens, curves."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from strategy_engine.models import StrategyLeg, Underlying, PricingAssumptions
from strategy_engine.payoff import payoff_at_expiration, strategy_payoff_at_expiration
from strategy_engine.metrics import compute_breakevens, compute_max_profit_loss, compute_capital_required, compute_risk_reward
from strategy_engine.pricing import leg_entry_cashflow
from strategy_engine.curve import expiration_curve, default_price_grid


def option_leg(option_type, strike, action, entry_price, iv=0.30, qty=1, exp="2026-06-20"):
    return StrategyLeg(
        instrument="option", option_type=option_type, action=action,
        quantity=qty, strike=strike, entry_price=entry_price,
        expiration=exp, iv=iv, multiplier=100,
    )


def stock_leg(action, entry_price, qty=100):
    return StrategyLeg(
        instrument="stock", action=action,
        quantity=qty, entry_price=entry_price,
    )


# ---------------------------------------------------------------------------
# Payoff at expiration
# ---------------------------------------------------------------------------

class TestPayoff:
    def test_long_call_itm(self):
        leg = option_leg("call", 100, "buy", 5.0)
        assert payoff_at_expiration(leg, 120) == pytest.approx(1500, abs=1)

    def test_long_call_otm(self):
        leg = option_leg("call", 100, "buy", 5.0)
        assert payoff_at_expiration(leg, 90) == pytest.approx(-500, abs=1)

    def test_short_call_otm(self):
        leg = option_leg("call", 100, "sell", 5.0)
        assert payoff_at_expiration(leg, 90) == pytest.approx(500, abs=1)

    def test_short_call_itm(self):
        leg = option_leg("call", 100, "sell", 5.0)
        assert payoff_at_expiration(leg, 120) == pytest.approx(-1500, abs=1)

    def test_long_put_itm(self):
        leg = option_leg("put", 100, "buy", 4.0)
        assert payoff_at_expiration(leg, 80) == pytest.approx(1600, abs=1)

    def test_stock_buy(self):
        leg = stock_leg("buy", 100, 100)
        assert payoff_at_expiration(leg, 110) == pytest.approx(1000, abs=1)

    def test_stock_sell(self):
        leg = stock_leg("sell", 100, 100)
        assert payoff_at_expiration(leg, 110) == pytest.approx(-1000, abs=1)


class TestStrategyPayoff:
    def test_call_debit_spread(self):
        legs = [
            option_leg("call", 100, "buy", 6.0),
            option_leg("call", 110, "sell", 2.0),
        ]
        # At 120: min(max(120-100,0),10) - 4 = 6 -> 600
        assert strategy_payoff_at_expiration(legs, 120) == pytest.approx(600, abs=1)
        # At 80: -4 -> -400
        assert strategy_payoff_at_expiration(legs, 80) == pytest.approx(-400, abs=1)

    def test_iron_condor(self):
        legs = [
            option_leg("put", 85, "buy", 0.50),
            option_leg("put", 90, "sell", 1.50),
            option_leg("call", 110, "sell", 1.50),
            option_leg("call", 115, "buy", 0.50),
        ]
        # Center: keep credit = 2.00 * 100 = 200
        assert strategy_payoff_at_expiration(legs, 100) == pytest.approx(200, abs=1)
        # Below wings: max loss
        assert strategy_payoff_at_expiration(legs, 80) == pytest.approx(-300, abs=1)


# ---------------------------------------------------------------------------
# Entry cashflow
# ---------------------------------------------------------------------------

class TestEntryCashflow:
    def test_buy_call(self):
        leg = option_leg("call", 100, "buy", 5.0)
        cf = leg_entry_cashflow(leg)
        assert cf == pytest.approx(-500, abs=1)  # cash out

    def test_sell_call(self):
        leg = option_leg("call", 100, "sell", 5.0)
        cf = leg_entry_cashflow(leg)
        assert cf == pytest.approx(500, abs=1)  # cash in

    def test_buy_stock(self):
        leg = stock_leg("buy", 150, 100)
        cf = leg_entry_cashflow(leg)
        assert cf == pytest.approx(-15000, abs=1)


# ---------------------------------------------------------------------------
# Breakevens
# ---------------------------------------------------------------------------

class TestBreakevens:
    def test_long_call_breakeven(self):
        legs = [option_leg("call", 100, "buy", 5.0)]
        bes = compute_breakevens(legs, 100)
        assert len(bes) == 1
        assert bes[0] == pytest.approx(105, abs=0.01)

    def test_long_put_breakeven(self):
        legs = [option_leg("put", 100, "buy", 4.0)]
        bes = compute_breakevens(legs, 100)
        assert len(bes) == 1
        assert bes[0] == pytest.approx(96, abs=0.01)

    def test_call_debit_spread_breakeven(self):
        legs = [
            option_leg("call", 100, "buy", 6.0),
            option_leg("call", 110, "sell", 2.0),
        ]
        bes = compute_breakevens(legs, 100)
        assert len(bes) == 1
        assert bes[0] == pytest.approx(104, abs=0.01)

    def test_iron_condor_two_breakevens(self):
        legs = [
            option_leg("put", 85, "buy", 0.50),
            option_leg("put", 90, "sell", 1.50),
            option_leg("call", 110, "sell", 1.50),
            option_leg("call", 115, "buy", 0.50),
        ]
        bes = compute_breakevens(legs, 100)
        assert len(bes) == 2
        assert bes[0] == pytest.approx(88, abs=0.01)
        assert bes[1] == pytest.approx(112, abs=0.01)


# ---------------------------------------------------------------------------
# Max profit / loss
# ---------------------------------------------------------------------------

class TestMaxProfitLoss:
    def test_long_call_unlimited_profit(self):
        legs = [option_leg("call", 100, "buy", 5.0)]
        mp, ml = compute_max_profit_loss(legs, 100)
        assert mp is None  # unlimited
        assert ml == pytest.approx(-500, abs=1)

    def test_call_debit_spread_defined_risk(self):
        legs = [
            option_leg("call", 100, "buy", 6.0),
            option_leg("call", 110, "sell", 2.0),
        ]
        mp, ml = compute_max_profit_loss(legs, 100)
        assert mp == pytest.approx(600, abs=1)
        assert ml == pytest.approx(-400, abs=1)

    def test_short_call_unlimited_loss(self):
        legs = [option_leg("call", 100, "sell", 5.0)]
        mp, ml = compute_max_profit_loss(legs, 100)
        assert ml is None  # unlimited loss
        assert mp == pytest.approx(500, abs=1)


# ---------------------------------------------------------------------------
# Capital required
# ---------------------------------------------------------------------------

class TestCapitalRequired:
    def test_defined_risk(self):
        cap, margin, method = compute_capital_required(-400, -400)
        assert cap == pytest.approx(400, abs=1)
        assert margin is False

    def test_undefined_risk(self):
        cap, margin, method = compute_capital_required(None, 500)
        assert margin is True

    def test_credit_strategy_unlimited_risk(self):
        cap, margin, method = compute_capital_required(None, 200)
        assert margin is True
        assert cap == 0.0  # net credit, no cash outlay


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------

class TestCurves:
    def test_expiration_curve_length(self):
        legs = [option_leg("call", 100, "buy", 5.0)]
        curve = expiration_curve(legs, 100, points=50)
        assert len(curve) == 50

    def test_price_grid_deterministic(self):
        _, _, grid = default_price_grid(100, [90, 100, 110], points=100)
        assert len(grid) == 100
        assert grid[0] > 0
        assert grid[-1] > grid[0]


# ---------------------------------------------------------------------------
# Stock legs in strategies
# ---------------------------------------------------------------------------

class TestStockLegs:
    def test_covered_call_payoff(self):
        """Covered call: buy 100 shares + sell 1 call."""
        legs = [
            stock_leg("buy", 100, 100),
            option_leg("call", 105, "sell", 3.0),
        ]
        # At 110: stock profit = 1000, call loss = (110-105-3)*100 = -200 -> total 800
        pl = strategy_payoff_at_expiration(legs, 110)
        assert pl == pytest.approx(800, abs=1)

        # At 95: stock loss = -500, call profit = 300 -> total -200
        pl = strategy_payoff_at_expiration(legs, 95)
        assert pl == pytest.approx(-200, abs=1)
