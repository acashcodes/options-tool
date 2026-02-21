"""Greeks Stress Test Suite

Per spec requirements, validates Black-Scholes implementation with:
1. Benchmark against known values
2. Boundary condition tests
3. Sensitivity checks
4. Put-call parity verification

Run: python test_greeks.py
"""

from __future__ import annotations

import math
import sys

from greeks import compute_greeks, bs_price, delta, gamma, theta, vega, prob_itm


PASS = 0
FAIL = 0
RESULTS = []


def check(name: str, actual, expected, tol=0.01, unit=""):
    """Check a value against expected within tolerance."""
    global PASS, FAIL
    if actual is None:
        ok = False
        diff = "None"
    elif isinstance(expected, str):
        # Descriptive checks like "> 0.95"
        if expected.startswith(">"):
            ok = actual > float(expected[1:])
        elif expected.startswith("<"):
            ok = actual < float(expected[1:])
        elif expected.startswith("~"):
            target = float(expected[1:])
            ok = abs(actual - target) <= tol
        else:
            ok = False
        diff = f"{actual:.6f} vs {expected}"
    else:
        ok = abs(actual - expected) <= tol
        diff = f"{actual:.6f} vs {expected:.6f} (diff={abs(actual - expected):.6f})"

    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1

    result = f"  [{status}] {name}: {diff}{' ' + unit if unit else ''}"
    RESULTS.append(result)
    print(result)


def section(title: str):
    header = f"\n{'=' * 60}\n{title}\n{'=' * 60}"
    RESULTS.append(header)
    print(header)


# =====================================================================
# 1. BENCHMARK AGAINST KNOWN VALUES
# =====================================================================
def test_benchmark():
    section("1. BENCHMARK: Known-value comparisons")

    # Test case: S=100, K=100, t=30/365, r=5%, σ=30%
    # Expected from standard BS calculators:
    #   Call price ≈ 3.63, Delta ≈ 0.536
    #   Put price ≈ 3.22, Delta ≈ -0.464
    S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30

    call = compute_greeks(S, K, t, r, sigma, "call")
    put = compute_greeks(S, K, t, r, sigma, "put")

    check("Call price (ATM 30d)", call["price"], 3.63, tol=0.05)
    check("Call delta (ATM 30d)", call["delta"], 0.536, tol=0.02)
    check("Call gamma (ATM 30d)", call["gamma"], 0.046, tol=0.005)
    check("Call vega (ATM 30d)", call["vega"], 0.114, tol=0.01)
    check("Call theta (ATM 30d)", call["theta"], "<0")

    check("Put price (ATM 30d)", put["price"], 3.22, tol=0.05)
    check("Put delta (ATM 30d)", put["delta"], -0.464, tol=0.02)

    # AAPL-like: S=175, K=180, t=45/365, r=5%, σ=25% (OTM call)
    S2, K2, t2, r2, sigma2 = 175, 180, 45 / 365, 0.05, 0.25
    otm_call = compute_greeks(S2, K2, t2, r2, sigma2, "call")
    check("OTM call price (175/180 45d)", otm_call["price"], "> 1.5")
    check("OTM call delta (175/180 45d)", otm_call["delta"], "< 0.50")
    check("OTM call delta > 0", otm_call["delta"], "> 0")

    # SPY-like: S=450, K=440, t=30/365, r=5%, σ=18% (ITM call)
    S3, K3, t3, r3, sigma3 = 450, 440, 30 / 365, 0.05, 0.18
    itm_call = compute_greeks(S3, K3, t3, r3, sigma3, "call")
    check("ITM call price (450/440 30d)", itm_call["price"], "> 11")
    check("ITM call delta (450/440 30d)", itm_call["delta"], "> 0.70")


# =====================================================================
# 2. BOUNDARY CONDITION TESTS
# =====================================================================
def test_boundaries():
    section("2. BOUNDARY CONDITIONS")

    r, sigma = 0.05, 0.30

    # 2a: Deep ITM call — delta ≈ 1.0
    deep_itm = compute_greeks(200, 100, 30 / 365, r, sigma, "call")
    check("Deep ITM call delta → ~1.0", deep_itm["delta"], "~1.0", tol=0.02)
    check("Deep ITM call price ≈ intrinsic", deep_itm["price"], "> 99")

    # 2b: Deep OTM call — delta ≈ 0.0
    deep_otm = compute_greeks(50, 100, 30 / 365, r, sigma, "call")
    check("Deep OTM call delta → ~0.0", deep_otm["delta"], "~0.0", tol=0.02)
    check("Deep OTM call price → ~0", deep_otm["price"], "< 0.01")

    # 2c: Deep ITM put — delta ≈ -1.0
    deep_itm_put = compute_greeks(50, 100, 30 / 365, r, sigma, "put")
    check("Deep ITM put delta → ~-1.0", deep_itm_put["delta"], "~-1.0", tol=0.02)

    # 2d: Deep OTM put — delta ≈ 0.0
    deep_otm_put = compute_greeks(200, 100, 30 / 365, r, sigma, "put")
    check("Deep OTM put delta → ~0.0", deep_otm_put["delta"], "~0.0", tol=0.02)

    # 2e: Near expiration (1 DTE) ATM — gamma should spike, delta ≈ 0.5
    near_exp = compute_greeks(100, 100, 1 / 365, r, sigma, "call")
    near_gamma = near_exp["gamma"]
    normal_gamma = compute_greeks(100, 100, 30 / 365, r, sigma, "call")["gamma"]
    check("1 DTE ATM delta → ~0.5", near_exp["delta"], "~0.5", tol=0.05)
    check("1 DTE gamma > 30 DTE gamma", near_gamma, f">{normal_gamma}")
    check("1 DTE theta more negative", near_exp["theta"], f"<{compute_greeks(100, 100, 30/365, r, sigma, 'call')['theta']}")

    # 2f: Long-dated (1 year) — small theta, large vega
    long_dated = compute_greeks(100, 100, 1.0, r, sigma, "call")
    short_dated = compute_greeks(100, 100, 30 / 365, r, sigma, "call")
    check("1Y theta < 30d theta (less negative per day)", long_dated["theta"], f">{short_dated['theta']}")
    check("1Y vega > 30d vega", long_dated["vega"], f">{short_dated['vega']}")


# =====================================================================
# 3. PUT-CALL PARITY
# =====================================================================
def test_put_call_parity():
    section("3. PUT-CALL PARITY")

    test_cases = [
        (100, 100, 30 / 365, 0.05, 0.30),
        (175, 180, 45 / 365, 0.05, 0.25),
        (450, 440, 90 / 365, 0.05, 0.18),
        (50, 60, 180 / 365, 0.04, 0.40),
    ]

    for S, K, t, r, sigma in test_cases:
        call = compute_greeks(S, K, t, r, sigma, "call")
        put = compute_greeks(S, K, t, r, sigma, "put")

        # Delta parity: call_delta - put_delta = 1
        delta_parity = call["delta"] - put["delta"]
        check(f"Delta parity S={S} K={K}", delta_parity, 1.0, tol=0.001)

        # Price parity: C - P = S - K*e^(-rt)
        price_parity = call["price"] - put["price"]
        expected_parity = S - K * math.exp(-r * t)
        check(f"Price parity S={S} K={K}", price_parity, expected_parity, tol=0.01)

        # Gamma should be equal
        check(f"Gamma equal S={S} K={K}", call["gamma"], put["gamma"], tol=0.0001)

        # Vega should be equal
        check(f"Vega equal S={S} K={K}", call["vega"], put["vega"], tol=0.0001)


# =====================================================================
# 4. SENSITIVITY CHECKS
# =====================================================================
def test_sensitivity():
    section("4. SENSITIVITY CHECKS")

    S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30

    # 4a: Delta predicts price change for $1 move
    call_price_0 = bs_price(S, K, t, r, sigma, "call")
    call_delta_0 = delta(S, K, t, r, sigma, "call")
    call_price_1 = bs_price(S + 1, K, t, r, sigma, "call")
    actual_change = call_price_1 - call_price_0
    predicted_change = call_delta_0
    check("Delta predicts $1 move", actual_change, predicted_change, tol=0.03)

    # 4b: Vega predicts price change for 1% IV increase
    call_vega_0 = vega(S, K, t, r, sigma)
    call_price_iv_up = bs_price(S, K, t, r, sigma + 0.01, "call")
    actual_iv_change = call_price_iv_up - call_price_0
    check("Vega predicts 1% IV change", actual_iv_change, call_vega_0, tol=0.005)

    # 4c: Theta predicts price change for 1 day passage
    dt = 1 / 365
    call_theta_0 = theta(S, K, t, r, sigma, "call")
    call_price_next_day = bs_price(S, K, t - dt, r, sigma, "call")
    actual_decay = call_price_next_day - call_price_0
    check("Theta predicts 1-day decay", actual_decay, call_theta_0, tol=0.01)

    # 4d: Gamma predicts delta change for $1 move
    gamma_0 = gamma(S, K, t, r, sigma)
    delta_after = delta(S + 1, K, t, r, sigma, "call")
    actual_delta_change = delta_after - call_delta_0
    check("Gamma predicts delta change", actual_delta_change, gamma_0, tol=0.005)


# =====================================================================
# 5. PROBABILITY OF PROFIT
# =====================================================================
def test_probability():
    section("5. PROBABILITY OF PROFIT")

    S, K, t, r, sigma = 100, 100, 30 / 365, 0.05, 0.30

    # ATM call P(ITM) ≈ delta ≈ 0.5 (rough approximation)
    p_call = prob_itm(S, K, t, r, sigma, "call")
    check("ATM call P(ITM) ≈ 0.5", p_call, "~0.5", tol=0.06)

    # Deep ITM call should have high probability
    p_deep_itm = prob_itm(200, 100, 30 / 365, r, sigma, "call")
    check("Deep ITM call P(ITM) → ~1.0", p_deep_itm, "> 0.99")

    # Deep OTM call should have low probability
    p_deep_otm = prob_itm(50, 100, 30 / 365, r, sigma, "call")
    check("Deep OTM call P(ITM) → ~0.0", p_deep_otm, "< 0.01")

    # Put probability = 1 - call probability for same strike
    p_put = prob_itm(S, K, t, r, sigma, "put")
    check("P(call ITM) + P(put ITM) = 1", p_call + p_put, 1.0, tol=0.001)


# =====================================================================
# 6. CROSS-VALIDATION AGAINST MIBIAN
# =====================================================================
def test_cross_validation():
    section("6. CROSS-VALIDATION: Our implementation vs mibian library")

    try:
        import mibian
    except ImportError:
        print("  [SKIP] mibian not installed — run: pip install mibian")
        return

    test_cases = [
        # (S, K, r%, DTE_days, sigma%)
        (100, 100, 5, 30, 30, "ATM 30d"),
        (175, 180, 5, 45, 25, "OTM call 45d"),
        (450, 440, 5, 30, 18, "ITM call 30d"),
        (50, 60, 4, 180, 40, "Deep OTM 180d"),
        (300, 300, 5, 365, 35, "ATM 1Y LEAP"),
    ]

    for S, K, r_pct, dte, sigma_pct, label in test_cases:
        # Our implementation
        t = dte / 365.0
        r = r_pct / 100.0
        sigma = sigma_pct / 100.0
        ours = compute_greeks(S, K, t, r, sigma, "call")
        ours_put = compute_greeks(S, K, t, r, sigma, "put")

        # mibian: takes [underlying, strike, interest_rate%, DTE], volatility=%
        mb = mibian.BS([S, K, r_pct, dte], volatility=sigma_pct)

        check(f"[{label}] Call price", ours["price"], mb.callPrice, tol=0.02)
        check(f"[{label}] Put price", ours_put["price"], mb.putPrice, tol=0.02)
        check(f"[{label}] Call delta", ours["delta"], mb.callDelta, tol=0.005)
        check(f"[{label}] Put delta", ours_put["delta"], mb.putDelta, tol=0.005)
        check(f"[{label}] Gamma", ours["gamma"], mb.gamma, tol=0.002)
        check(f"[{label}] Vega", ours["vega"], mb.vega, tol=0.005)
        # Theta: mibian returns per-day theta for calls
        check(f"[{label}] Call theta", ours["theta"], mb.callTheta, tol=0.01)


# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("BLACK-SCHOLES GREEKS STRESS TEST SUITE")
    print("=" * 60)

    test_benchmark()
    test_boundaries()
    test_put_call_parity()
    test_sensitivity()
    test_probability()
    test_cross_validation()

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} PASSED, {FAIL} FAILED out of {PASS + FAIL} tests")
    print("=" * 60)

    if FAIL > 0:
        print("\nFAILED TESTS:")
        for r in RESULTS:
            if "[FAIL]" in r:
                print(r)
        sys.exit(1)
    else:
        print("\nALL TESTS PASSED ✓")
        sys.exit(0)
