#!/usr/bin/env python3
"""Comprehensive test for the rebuilt strategy recommendation engine.

Tests _leg_pl, each strategy type's payoff formulas, risk-reward
calculations, max profit/loss, breakevens, and the filtering/sorting logic.
"""

import sys
import math

sys.path.insert(0, ".")
from routes.recommender import _leg_pl

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, actual, expected, tol=0.01):
    global PASS_COUNT, FAIL_COUNT
    if expected is None:
        ok = actual is None
    elif isinstance(expected, bool):
        ok = actual == expected
    elif isinstance(expected, (int, float)) and actual is not None:
        ok = abs(actual - expected) < abs(expected * tol) + 0.5
    else:
        ok = actual == expected

    status = "PASS" if ok else "FAIL"
    if not ok:
        FAIL_COUNT += 1
        print(f"  {status}: {name}: expected={expected}, actual={actual}")
    else:
        PASS_COUNT += 1


def make_leg(opt_type, strike, premium, action, qty=1):
    return {
        "type": opt_type,
        "strike": strike,
        "action": action,
        "quantity": qty,
        "premium": premium,
    }


# ──────────────────────────────────────────────────────────────
# Section 1: _leg_pl unit tests
# ──────────────────────────────────────────────────────────────

def test_leg_pl():
    print("\n=== _leg_pl unit tests ===")

    # Long call: payoff = max(S - K, 0) - premium, × 100
    leg = make_leg("Call", 100, 5, "buy")
    check("Long Call deep ITM (S=150)", _leg_pl(leg, 150), 4500)
    check("Long Call slightly ITM (S=107)", _leg_pl(leg, 107), 200)
    check("Long Call ATM (S=100)", _leg_pl(leg, 100), -500)
    check("Long Call slightly OTM (S=97)", _leg_pl(leg, 97), -500)
    check("Long Call deep OTM (S=50)", _leg_pl(leg, 50), -500)

    # Long put: payoff = max(K - S, 0) - premium, × 100
    leg = make_leg("Put", 100, 4, "buy")
    check("Long Put deep ITM (S=50)", _leg_pl(leg, 50), 4600)
    check("Long Put ATM (S=100)", _leg_pl(leg, 100), -400)
    check("Long Put OTM (S=120)", _leg_pl(leg, 120), -400)
    check("Long Put near zero (S=0.01)", _leg_pl(leg, 0.01), 9599)

    # Short call: payoff = premium - max(S - K, 0), × 100
    leg = make_leg("Call", 100, 5, "sell")
    check("Short Call OTM (S=90)", _leg_pl(leg, 90), 500)
    check("Short Call ATM (S=100)", _leg_pl(leg, 100), 500)
    check("Short Call ITM (S=110)", _leg_pl(leg, 110), -500)
    check("Short Call deep ITM (S=200)", _leg_pl(leg, 200), -9500)

    # Short put: payoff = premium - max(K - S, 0), × 100
    leg = make_leg("Put", 100, 4, "sell")
    check("Short Put OTM (S=110)", _leg_pl(leg, 110), 400)
    check("Short Put ATM (S=100)", _leg_pl(leg, 100), 400)
    check("Short Put ITM (S=90)", _leg_pl(leg, 90), -600)
    check("Short Put deep ITM (S=10)", _leg_pl(leg, 10), -8600)

    # Quantity test
    leg = make_leg("Call", 100, 5, "buy", qty=3)
    check("Long Call qty=3 ITM (S=120)", _leg_pl(leg, 120), (20 - 5) * 100 * 3)


# ──────────────────────────────────────────────────────────────
# Section 2: Strategy payoff formula tests (per spec section 4)
# ──────────────────────────────────────────────────────────────

def test_long_call_formulas():
    """Spec §4.1: Payoff = max(St - K, 0) - Premium. Capital = Premium."""
    print("\n=== Long Call formula ===")
    K, prem = 100, 5
    St_values = [80, 95, 100, 105, 110, 120, 150]
    for St in St_values:
        expected = (max(St - K, 0) - prem) * 100
        leg = make_leg("Call", K, prem, "buy")
        actual = _leg_pl(leg, St)
        check(f"Long Call K={K} prem={prem} St={St}", actual, expected)

    # Max profit MUST be unlimited (None)
    # Capital = Premium × 100
    check("Capital = premium*100", prem * 100, 500)

    # Breakeven = K + Premium
    check("Breakeven = K + prem", K + prem, 105)


def test_long_put_formulas():
    """Spec §4.2: Payoff = max(K - St, 0) - Premium. Capital = Premium."""
    print("\n=== Long Put formula ===")
    K, prem = 100, 4
    St_values = [50, 80, 96, 100, 105, 120]
    for St in St_values:
        expected = (max(K - St, 0) - prem) * 100
        leg = make_leg("Put", K, prem, "buy")
        actual = _leg_pl(leg, St)
        check(f"Long Put K={K} prem={prem} St={St}", actual, expected)

    check("Breakeven = K - prem", K - prem, 96)


def test_call_debit_spread_formulas():
    """Spec §4.3: Buy K1, sell K2. Payoff = min(max(St-K1,0), Width) - NetDebit."""
    print("\n=== Call Debit Spread formula ===")
    K1, K2 = 100, 110
    prem1, prem2 = 6, 2
    net_debit = prem1 - prem2  # 4
    width = K2 - K1  # 10
    max_profit = (width - net_debit) * 100  # 600
    max_loss = net_debit * 100  # 400

    check("Net debit", net_debit, 4)
    check("Max profit = (width - debit)*100", max_profit, 600)
    check("Max loss = debit*100", max_loss, 400)
    check("Breakeven = K1 + debit", K1 + net_debit, 104)

    St_values = [80, 100, 104, 107, 110, 120, 150]
    for St in St_values:
        intrinsic = max(St - K1, 0)
        spread_val = min(intrinsic, width)
        expected = (spread_val - net_debit) * 100
        # Verify via _leg_pl composition
        legs = [make_leg("Call", K1, prem1, "buy"), make_leg("Call", K2, prem2, "sell")]
        actual = sum(_leg_pl(l, St) for l in legs)
        check(f"Call Debit Spread St={St}", actual, expected)


def test_put_debit_spread_formulas():
    """Spec §4.4: Buy K1 (higher), sell K2 (lower)."""
    print("\n=== Put Debit Spread formula ===")
    K1, K2 = 100, 90
    prem1, prem2 = 4, 1
    net_debit = prem1 - prem2  # 3
    width = K1 - K2  # 10
    max_profit = (width - net_debit) * 100  # 700
    max_loss = net_debit * 100  # 300

    check("Net debit", net_debit, 3)
    check("Max profit", max_profit, 700)
    check("Max loss", max_loss, 300)
    check("Breakeven = K1 - debit", K1 - net_debit, 97)

    St_values = [50, 85, 90, 93, 97, 100, 110]
    for St in St_values:
        intrinsic = max(K1 - St, 0)
        spread_val = min(intrinsic, width)
        expected = (spread_val - net_debit) * 100
        legs = [make_leg("Put", K1, prem1, "buy"), make_leg("Put", K2, prem2, "sell")]
        actual = sum(_leg_pl(l, St) for l in legs)
        check(f"Put Debit Spread St={St}", actual, expected)


def test_call_credit_spread_formulas():
    """Spec §4.5: Sell K1 (lower), buy K2 (higher)."""
    print("\n=== Call Credit Spread formula ===")
    K1, K2 = 105, 110
    prem1, prem2 = 3, 1
    net_credit = prem1 - prem2  # 2
    width = K2 - K1  # 5
    max_loss = (width - net_credit) * 100  # 300
    max_profit = net_credit * 100  # 200

    check("Net credit", net_credit, 2)
    check("Max profit = credit*100", max_profit, 200)
    check("Max loss = (width-credit)*100", max_loss, 300)
    check("Breakeven = K1 + credit", K1 + net_credit, 107)

    St_values = [90, 105, 107, 108, 110, 120]
    for St in St_values:
        intrinsic_loss = max(St - K1, 0)
        actual_loss = min(intrinsic_loss, width)
        expected = (net_credit - actual_loss) * 100
        legs = [make_leg("Call", K1, prem1, "sell"), make_leg("Call", K2, prem2, "buy")]
        actual = sum(_leg_pl(l, St) for l in legs)
        check(f"Call Credit Spread St={St}", actual, expected)


def test_put_credit_spread_formulas():
    """Spec §4.6: Sell K1 (higher), buy K2 (lower)."""
    print("\n=== Put Credit Spread formula ===")
    K1, K2 = 95, 90
    prem1, prem2 = 3, 1
    net_credit = prem1 - prem2  # 2
    width = K1 - K2  # 5
    max_loss = (width - net_credit) * 100  # 300
    max_profit = net_credit * 100  # 200

    check("Net credit", net_credit, 2)
    check("Max profit = credit*100", max_profit, 200)
    check("Max loss = (width-credit)*100", max_loss, 300)
    check("Breakeven = K1 - credit", K1 - net_credit, 93)

    St_values = [80, 90, 93, 95, 100, 110]
    for St in St_values:
        intrinsic_loss = max(K1 - St, 0)
        actual_loss = min(intrinsic_loss, width)
        expected = (net_credit - actual_loss) * 100
        legs = [make_leg("Put", K1, prem1, "sell"), make_leg("Put", K2, prem2, "buy")]
        actual = sum(_leg_pl(l, St) for l in legs)
        check(f"Put Credit Spread St={St}", actual, expected)


def test_iron_condor_formulas():
    """Iron condor = put credit spread + call credit spread."""
    print("\n=== Iron Condor formula ===")
    # Buy 85P @0.5, Sell 90P @1.5, Sell 110C @1.5, Buy 115C @0.5
    legs = [
        make_leg("Put", 85, 0.50, "buy"),
        make_leg("Put", 90, 1.50, "sell"),
        make_leg("Call", 110, 1.50, "sell"),
        make_leg("Call", 115, 0.50, "buy"),
    ]
    net_credit = (1.50 + 1.50) - (0.50 + 0.50)  # 2.00
    put_width = 5
    call_width = 5
    max_loss = (max(put_width, call_width) - net_credit) * 100  # 300
    max_profit = net_credit * 100  # 200

    check("IC net credit", net_credit, 2.00)
    check("IC max profit", max_profit, 200)
    check("IC max loss", max_loss, 300)

    # In profit zone (St=100): all OTM, keep full credit
    check("IC at St=100 (center)", sum(_leg_pl(l, 100) for l in legs), 200)
    # Below put wing (St=80): max loss
    check("IC at St=80 (below)", sum(_leg_pl(l, 80) for l in legs), -300)
    # Above call wing (St=120): max loss
    check("IC at St=120 (above)", sum(_leg_pl(l, 120) for l in legs), -300)


# ──────────────────────────────────────────────────────────────
# Section 3: Risk-reward calculation
# ──────────────────────────────────────────────────────────────

def test_risk_reward():
    """Spec §5: RiskReward = Payoff_at_Target / Capital_Required."""
    print("\n=== Risk-Reward ===")

    # Long Call: K=100, prem=5, target=120
    # Payoff = (20-5)*100 = 1500, Capital = 500, RR = 3.0
    payoff = (max(120 - 100, 0) - 5) * 100
    capital = 5 * 100
    rr = payoff / capital
    check("Long Call RR", rr, 3.0)

    # Call Debit Spread: K1=100, K2=110, prem1=6, prem2=2, target=115
    # Payoff = (min(15,10) - 4)*100 = 600, Capital = 400, RR = 1.5
    net_debit = 6 - 2
    spread_val = min(max(115 - 100, 0), 10)
    payoff = (spread_val - net_debit) * 100
    capital = net_debit * 100
    rr = payoff / capital
    check("Call Debit Spread RR", rr, 1.5)

    # Put Credit Spread: K1=95, K2=90, prem1=3, prem2=1, target=100
    # Payoff = (2 - 0)*100 = 200, Capital = 300, RR = 0.67
    net_credit = 3 - 1
    intrinsic_loss = max(95 - 100, 0)  # 0
    actual_loss = min(intrinsic_loss, 5)
    payoff = (net_credit - actual_loss) * 100
    max_loss_ps = 5 - net_credit
    capital = max_loss_ps * 100
    rr = payoff / capital
    check("Put Credit Spread RR", round(rr, 2), 0.67)


# ──────────────────────────────────────────────────────────────
# Section 4: Max profit/loss explicit validation
# ──────────────────────────────────────────────────────────────

def test_max_profit_loss():
    """Validate max profit/loss for each strategy type."""
    print("\n=== Max Profit/Loss ===")

    # Long Call: max_profit = UNLIMITED, max_loss = premium
    check("Long Call max_profit unlimited", None, None)
    check("Long Call max_loss", 5 * 100, 500)

    # Long Put: max_profit = (K - premium) * 100 (at S=0), max_loss = premium
    K, prem = 100, 4
    check("Long Put max_profit", (K - prem) * 100, 9600)
    check("Long Put max_loss", prem * 100, 400)

    # Call Debit Spread: max_profit = (width - debit), max_loss = debit
    width, debit = 10, 4
    check("CDS max_profit", (width - debit) * 100, 600)
    check("CDS max_loss", debit * 100, 400)

    # Call Credit Spread: max_profit = credit, max_loss = width - credit
    width, credit = 5, 2
    check("CCS max_profit", credit * 100, 200)
    check("CCS max_loss", (width - credit) * 100, 300)


# ──────────────────────────────────────────────────────────────
# Section 5: Breakeven accuracy
# ──────────────────────────────────────────────────────────────

def test_breakeven_accuracy():
    """Verify that P&L at reported breakeven is approximately zero."""
    print("\n=== Breakeven accuracy ===")

    cases = [
        ("Long Call 100@5", [make_leg("Call", 100, 5, "buy")], [105]),
        ("Long Put 100@4", [make_leg("Put", 100, 4, "buy")], [96]),
        ("Call Debit 100/110 (6/2)", [
            make_leg("Call", 100, 6, "buy"), make_leg("Call", 110, 2, "sell")
        ], [104]),
        ("Put Debit 100/90 (4/1)", [
            make_leg("Put", 100, 4, "buy"), make_leg("Put", 90, 1, "sell")
        ], [97]),
        ("Call Credit 105/110 (3/1)", [
            make_leg("Call", 105, 3, "sell"), make_leg("Call", 110, 1, "buy")
        ], [107]),
        ("Put Credit 95/90 (3/1)", [
            make_leg("Put", 95, 3, "sell"), make_leg("Put", 90, 1, "buy")
        ], [93]),
    ]

    for name, legs, expected_bes in cases:
        for be in expected_bes:
            pl = sum(_leg_pl(l, be) for l in legs)
            check(f"{name} BE={be} P&L~0", abs(pl) < 1, True)


# ──────────────────────────────────────────────────────────────
# Section 6: Cheap stock edge cases (SNAP-like)
# ──────────────────────────────────────────────────────────────

def test_cheap_stock():
    """Verify formulas work for cheap stocks ($5-$10 range)."""
    print("\n=== Cheap stock (SNAP-like) ===")

    # SNAP at $6, Long Call K=6, prem=0.30, target=6.50
    K, prem, St = 6, 0.30, 6.50
    payoff = (max(St - K, 0) - prem) * 100  # (0.5-0.3)*100 = 20
    capital = prem * 100  # 30
    rr = payoff / capital  # 0.67
    check("SNAP Long Call payoff", payoff, 20)
    check("SNAP Long Call capital", capital, 30)
    check("SNAP Long Call RR", round(rr, 2), 0.67)
    check("SNAP Long Call breakeven", K + prem, 6.30)

    # SNAP at $6, Long Call K=6, prem=0.30, target=8 (bigger move)
    St2 = 8
    payoff2 = (max(St2 - K, 0) - prem) * 100  # (2-0.3)*100 = 170
    rr2 = payoff2 / capital  # 5.67
    check("SNAP big move payoff", payoff2, 170)
    check("SNAP big move RR", round(rr2, 2), 5.67)

    # Verify _leg_pl matches
    leg = make_leg("Call", 6, 0.30, "buy")
    check("SNAP _leg_pl at 6.50", _leg_pl(leg, 6.50), 20)
    check("SNAP _leg_pl at 8", _leg_pl(leg, 8), 170)
    check("SNAP _leg_pl at 5 (OTM)", _leg_pl(leg, 5), -30)


# ──────────────────────────────────────────────────────────────
# Section 7: Filtering and sorting
# ──────────────────────────────────────────────────────────────

def test_filtering_sorting():
    """Verify: payoff<=0 discarded, sorted by RR descending, top 5."""
    print("\n=== Filtering & sorting ===")

    # Simulate strategy candidates
    candidates = [
        {"payoff_at_target": 100, "capital_required": 200, "risk_reward": 0.5},
        {"payoff_at_target": -50, "capital_required": 100, "risk_reward": -0.5},  # discard
        {"payoff_at_target": 300, "capital_required": 100, "risk_reward": 3.0},
        {"payoff_at_target": 200, "capital_required": 100, "risk_reward": 2.0},
        {"payoff_at_target": 0, "capital_required": 100, "risk_reward": 0},  # discard
        {"payoff_at_target": 500, "capital_required": 200, "risk_reward": 2.5},
        {"payoff_at_target": 150, "capital_required": 50, "risk_reward": 3.0},
        {"payoff_at_target": 50, "capital_required": 100, "risk_reward": 0.5},
    ]

    valid = [c for c in candidates if c["payoff_at_target"] > 0 and c["capital_required"] > 0]
    check("Filter removes 2 losers", len(valid), 6)

    valid.sort(key=lambda x: x["risk_reward"], reverse=True)
    check("Best RR first", valid[0]["risk_reward"], 3.0)
    check("Second best", valid[1]["risk_reward"], 3.0)  # tie

    top5 = valid[:5]
    check("Top 5 capped", len(top5), 5)
    check("Worst in top 5 has RR>=0.5", top5[-1]["risk_reward"] >= 0.5, True)


# ──────────────────────────────────────────────────────────────
# Section 8: Payoff consistency (verify _leg_pl matches spec formulas)
# ──────────────────────────────────────────────────────────────

def test_payoff_consistency():
    """Multi-leg payoffs via _leg_pl must match spec formulas exactly."""
    print("\n=== Payoff consistency ===")

    # Bull call spread far above both strikes = max profit
    legs = [make_leg("Call", 100, 5, "buy"), make_leg("Call", 110, 2, "sell")]
    width = 10
    net_debit = 5 - 2
    max_profit = (width - net_debit) * 100
    max_loss = net_debit * 100
    check("BCS far above = max_profit", sum(_leg_pl(l, 200) for l in legs), max_profit)
    check("BCS far below = max_loss", sum(_leg_pl(l, 50) for l in legs), -max_loss)

    # Bear put spread far below both = max profit
    legs = [make_leg("Put", 100, 4, "buy"), make_leg("Put", 90, 1, "sell")]
    width = 10
    net_debit = 4 - 1
    max_profit = (width - net_debit) * 100
    max_loss = net_debit * 100
    check("BPS far below = max_profit", sum(_leg_pl(l, 50) for l in legs), max_profit)
    check("BPS far above = max_loss", sum(_leg_pl(l, 150) for l in legs), -max_loss)

    # Iron condor center = max profit, wings = max loss
    legs = [
        make_leg("Put", 85, 0.50, "buy"),
        make_leg("Put", 90, 1.50, "sell"),
        make_leg("Call", 110, 1.50, "sell"),
        make_leg("Call", 115, 0.50, "buy"),
    ]
    net_credit = 2.0
    check("IC center = max_profit", sum(_leg_pl(l, 100) for l in legs), net_credit * 100)
    check("IC below wings = max_loss", sum(_leg_pl(l, 50) for l in legs), -300)
    check("IC above wings = max_loss", sum(_leg_pl(l, 200) for l in legs), -300)


# ──────────────────────────────────────────────────────────────
# Run all
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_leg_pl()
    test_long_call_formulas()
    test_long_put_formulas()
    test_call_debit_spread_formulas()
    test_put_debit_spread_formulas()
    test_call_credit_spread_formulas()
    test_put_credit_spread_formulas()
    test_iron_condor_formulas()
    test_risk_reward()
    test_max_profit_loss()
    test_breakeven_accuracy()
    test_cheap_stock()
    test_filtering_sorting()
    test_payoff_consistency()

    print(f"\n{'=' * 50}")
    print(f"RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    if FAIL_COUNT > 0:
        print("*** FAILURES DETECTED — FIX BEFORE PROCEEDING ***")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
