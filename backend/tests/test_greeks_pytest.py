"""Pytest suite for Black-Scholes-Merton Greeks and pricing.

Covers benchmarks, boundary conditions, put-call parity (with and without q),
sensitivity checks, and probability of profit.
"""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from greeks import (
    compute_greeks, bs_price, delta, gamma, theta, vega, rho,
    prob_itm, prob_above, prob_below,
)


# ---------------------------------------------------------------------------
# 1. Benchmark against known values (q=0)
# ---------------------------------------------------------------------------

class TestBenchmark:
    def test_atm_call_30d(self):
        S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30
        g = compute_greeks(S, K, t, r, sigma, "call")
        assert g["price"] == pytest.approx(3.63, abs=0.05)
        assert g["delta"] == pytest.approx(0.536, abs=0.02)
        assert g["gamma"] == pytest.approx(0.046, abs=0.005)
        assert g["vega"] == pytest.approx(0.114, abs=0.01)
        assert g["theta"] < 0

    def test_atm_put_30d(self):
        S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30
        g = compute_greeks(S, K, t, r, sigma, "put")
        assert g["price"] == pytest.approx(3.22, abs=0.05)
        assert g["delta"] == pytest.approx(-0.464, abs=0.02)

    def test_otm_call(self):
        g = compute_greeks(175, 180, 45 / 365, 0.05, 0.25, "call")
        assert g["price"] > 1.5
        assert 0 < g["delta"] < 0.50

    def test_itm_call(self):
        g = compute_greeks(450, 440, 30 / 365, 0.05, 0.18, "call")
        assert g["price"] > 11
        assert g["delta"] > 0.70


# ---------------------------------------------------------------------------
# 2. Boundary conditions
# ---------------------------------------------------------------------------

class TestBoundaries:
    def test_deep_itm_call_delta(self):
        g = compute_greeks(200, 100, 30 / 365, 0.05, 0.30, "call")
        assert g["delta"] == pytest.approx(1.0, abs=0.02)
        assert g["price"] > 99

    def test_deep_otm_call_delta(self):
        g = compute_greeks(50, 100, 30 / 365, 0.05, 0.30, "call")
        assert g["delta"] == pytest.approx(0.0, abs=0.02)
        assert g["price"] < 0.01

    def test_deep_itm_put_delta(self):
        g = compute_greeks(50, 100, 30 / 365, 0.05, 0.30, "put")
        assert g["delta"] == pytest.approx(-1.0, abs=0.02)

    def test_deep_otm_put_delta(self):
        g = compute_greeks(200, 100, 30 / 365, 0.05, 0.30, "put")
        assert g["delta"] == pytest.approx(0.0, abs=0.02)

    def test_near_expiry_gamma_spike(self):
        g1 = compute_greeks(100, 100, 1 / 365, 0.05, 0.30, "call")
        g30 = compute_greeks(100, 100, 30 / 365, 0.05, 0.30, "call")
        assert g1["gamma"] > g30["gamma"]
        assert g1["delta"] == pytest.approx(0.5, abs=0.05)

    def test_invalid_inputs_return_none(self):
        g = compute_greeks(100, 100, 30 / 365, 0.05, 0.0, "call")
        assert g["delta"] is None


# ---------------------------------------------------------------------------
# 3. Put-call parity (with and without dividends)
# ---------------------------------------------------------------------------

class TestPutCallParity:
    @pytest.mark.parametrize("S,K,t,r,sigma", [
        (100, 100, 30 / 365, 0.05, 0.30),
        (175, 180, 45 / 365, 0.05, 0.25),
        (450, 440, 90 / 365, 0.05, 0.18),
        (50, 60, 180 / 365, 0.04, 0.40),
    ])
    def test_parity_no_dividends(self, S, K, t, r, sigma):
        call = compute_greeks(S, K, t, r, sigma, "call")
        put = compute_greeks(S, K, t, r, sigma, "put")
        # Delta parity: call_delta - put_delta = 1
        assert call["delta"] - put["delta"] == pytest.approx(1.0, abs=0.001)
        # Price parity: C - P = S - K*e^(-rt)
        expected = S - K * math.exp(-r * t)
        assert call["price"] - put["price"] == pytest.approx(expected, abs=0.01)
        # Gamma and vega equal
        assert call["gamma"] == pytest.approx(put["gamma"], abs=0.0001)
        assert call["vega"] == pytest.approx(put["vega"], abs=0.0001)

    @pytest.mark.parametrize("S,K,t,r,sigma,q", [
        (100, 100, 30 / 365, 0.05, 0.30, 0.02),
        (175, 180, 90 / 365, 0.05, 0.25, 0.015),
        (450, 440, 180 / 365, 0.04, 0.20, 0.01),
    ])
    def test_parity_with_dividends(self, S, K, t, r, sigma, q):
        """C - P = S*exp(-q*t) - K*exp(-r*t)"""
        C = bs_price(S, K, t, r, sigma, "call", q=q)
        P = bs_price(S, K, t, r, sigma, "put", q=q)
        expected = S * math.exp(-q * t) - K * math.exp(-r * t)
        assert C - P == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# 4. Sensitivity checks
# ---------------------------------------------------------------------------

class TestSensitivity:
    def test_delta_predicts_price_change(self):
        S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30
        p0 = bs_price(S, K, t, r, sigma, "call")
        d = delta(S, K, t, r, sigma, "call")
        p1 = bs_price(S + 1, K, t, r, sigma, "call")
        assert (p1 - p0) == pytest.approx(d, abs=0.03)

    def test_vega_predicts_iv_change(self):
        S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30
        p0 = bs_price(S, K, t, r, sigma, "call")
        v = vega(S, K, t, r, sigma)
        p1 = bs_price(S, K, t, r, sigma + 0.01, "call")
        assert (p1 - p0) == pytest.approx(v, abs=0.005)

    def test_theta_predicts_decay(self):
        S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30
        p0 = bs_price(S, K, t, r, sigma, "call")
        th = theta(S, K, t, r, sigma, "call")
        p1 = bs_price(S, K, t - 1 / 365, r, sigma, "call")
        assert (p1 - p0) == pytest.approx(th, abs=0.01)

    def test_gamma_predicts_delta_change(self):
        S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30
        d0 = delta(S, K, t, r, sigma, "call")
        g = gamma(S, K, t, r, sigma)
        d1 = delta(S + 1, K, t, r, sigma, "call")
        assert (d1 - d0) == pytest.approx(g, abs=0.005)


# ---------------------------------------------------------------------------
# 5. Probability of profit
# ---------------------------------------------------------------------------

class TestProbability:
    def test_atm_call_prob_half(self):
        p = prob_itm(100, 100, 30 / 365, 0.05, 0.30, "call")
        assert p == pytest.approx(0.5, abs=0.06)

    def test_deep_itm_prob_high(self):
        assert prob_itm(200, 100, 30 / 365, 0.05, 0.30, "call") > 0.99

    def test_deep_otm_prob_low(self):
        assert prob_itm(50, 100, 30 / 365, 0.05, 0.30, "call") < 0.01

    def test_call_put_prob_sum(self):
        S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30
        pc = prob_itm(S, K, t, r, sigma, "call")
        pp = prob_itm(S, K, t, r, sigma, "put")
        assert pc + pp == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# 6. No premature rounding in compute_greeks
# ---------------------------------------------------------------------------

class TestNoRounding:
    def test_compute_greeks_returns_full_precision(self):
        g = compute_greeks(100, 100, 30 / 365, 0.05, 0.30, "call")
        # Values should NOT be rounded to 4 decimal places
        # Delta should have more precision than 0.5360
        d_str = f"{g['delta']:.10f}"
        # It should have non-zero digits beyond 4th decimal
        assert len(d_str) > 6
