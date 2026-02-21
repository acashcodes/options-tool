Options Strategy Recommendation Engine Specification

Purpose

This document defines the complete requirements for rebuilding the options strategy recommendation engine from scratch.

The goal is to construct a deterministic, math-consistent engine that:
	1.	Uses user-defined target price and target date.
	2.	Evaluates multiple option strategies.
	3.	Computes payoff strictly at the target price on the target date.
	4.	Ranks strategies by capital efficiency (risk-reward ratio).
	5.	Returns the top 5 strategies.

The engine must use real option chain data and correct payoff mathematics.

⸻

1. Core Objective

Given:
	•	Current stock price (S₀)
	•	Target stock price (Sᵗ)
	•	Target date (Tᵗ)
	•	Full options chain
	•	Current implied volatility

The engine must:
	•	Select appropriate expiration(s) near Tᵗ
	•	Construct viable strategies
	•	Calculate payoff at Sᵗ at expiration
	•	Rank strategies by:

RiskReward = Payoff_at_Target / Capital_Required


⸻

2. Critical Design Principles

2.1 Target-Driven Strategy Selection

The engine MUST use the target price to influence:
	•	Direction (bullish / bearish / neutral)
	•	Strike selection
	•	Strategy type

If Sᵗ > S₀ → Favor bullish strategies
If Sᵗ < S₀ → Favor bearish strategies
If Sᵗ ≈ S₀ → Consider neutral structures

Strike selection must NOT be arbitrary.

Strikes must be chosen relative to:
	•	Distance from S₀ to Sᵗ
	•	Time to expiration
	•	Implied volatility
	•	Available strike intervals

⸻

2.2 Expiration Selection

Select expiration(s) closest to target date Tᵗ.

Rules:
	•	Use expiration on or just after Tᵗ.
	•	If none exists, use nearest available.
	•	Do NOT mix expirations within a strategy.

⸻

3. Strategies to Evaluate

For each valid expiration, evaluate:
	1.	Long Call
	2.	Long Put
	3.	Call Debit Spread
	4.	Put Debit Spread
	5.	Call Credit Spread
	6.	Put Credit Spread

(Only include strategies aligned with direction.)

Optional:
7. Iron Condor (only if neutral bias)

⸻

4. Correct Payoff Formulas

All payoffs must be calculated at expiration at Sᵗ.

4.1 Long Call

Payoff = max(Sᵗ - K, 0) - Premium
Capital Required = Premium

Long calls have UNCAPPED upside.

⸻

4.2 Long Put

Payoff = max(K - Sᵗ, 0) - Premium
Capital Required = Premium


⸻

4.3 Call Debit Spread (Bullish)

Buy lower strike K1
Sell higher strike K2

Width = K2 - K1
Intrinsic = max(Sᵗ - K1, 0)
SpreadValue = min(Intrinsic, Width)

Payoff = SpreadValue - NetDebit
Capital Required = NetDebit

Profit is capped at Width - NetDebit.

⸻

4.4 Put Debit Spread (Bearish)

Buy higher strike K1
Sell lower strike K2

Width = K1 - K2
Intrinsic = max(K1 - Sᵗ, 0)
SpreadValue = min(Intrinsic, Width)

Payoff = SpreadValue - NetDebit
Capital Required = NetDebit


⸻

4.5 Call Credit Spread (Bearish)

Sell lower strike K1
Buy higher strike K2

MaxLoss = (K2 - K1) - NetCredit

IntrinsicLoss = max(Sᵗ - K1, 0)
ActualLoss = min(IntrinsicLoss, K2 - K1)

Payoff = NetCredit - ActualLoss
Capital Required = MaxLoss


⸻

4.6 Put Credit Spread (Bullish)

Sell higher strike K1
Buy lower strike K2

MaxLoss = (K1 - K2) - NetCredit

IntrinsicLoss = max(K1 - Sᵗ, 0)
ActualLoss = min(IntrinsicLoss, K1 - K2)

Payoff = NetCredit - ActualLoss
Capital Required = MaxLoss


⸻

5. Risk-Reward Calculation

For every strategy:

RiskReward = Payoff_at_Target / Capital_Required

Interpretation:

“How many dollars of profit do I make per $1 of capital if stock hits target?”

Rules:
	•	If Payoff <= 0 → discard strategy.
	•	Rank descending by RiskReward.
	•	Return top 5.

⸻

6. Strike Selection Logic

Strikes must be chosen systematically.

For bullish case (Sᵗ > S₀):
	•	Long Calls: evaluate strikes from ATM to moderately OTM.
	•	Debit Spreads: lower strike near ATM, upper strike near Sᵗ.
	•	Credit Spreads: sell strike just below Sᵗ.

For bearish case (Sᵗ < S₀):
	•	Mirror logic using puts.

Do NOT:
	•	Hardcode arbitrary strike distances.
	•	Use fixed percentage OTM rules without referencing target.

Strikes should be evaluated across a reasonable range and optimized by output metric.

⸻

7. Volatility Consideration

Use current implied volatility from the options chain.

While payoff at expiration ignores IV, IV should influence:
	•	Which expiration is selected.
	•	Whether debit vs credit spreads are preferable.
	•	Filtering out abnormally overpriced contracts.

Do NOT fabricate IV assumptions.

⸻

8. Output Structure

Each recommendation must include:
	•	Strategy Name
	•	Expiration Date
	•	Strikes Used
	•	Cost (Net Debit or Credit)
	•	Capital Required
	•	Payoff at Target
	•	Risk-Reward Ratio
	•	Max Profit
	•	Max Loss

Long calls must NOT show capped profit.

⸻

9. Validation Requirements

Before returning results:
	•	Confirm payoff math aligns with formulas above.
	•	Confirm spreads cap profit properly.
	•	Confirm long options do NOT cap profit.
	•	Confirm no negative capital values.
	•	Confirm expiration consistency.

If inconsistencies exist → do not return output.

⸻

10. Determinism

The engine must:
	•	Produce identical output given identical inputs.
	•	Avoid randomness.
	•	Avoid placeholder values.
	•	Use real chain data only.

⸻

Final Directive

Delete all previous recommendation logic.

Rebuild this engine from scratch using this specification as the single source of truth.

All calculations must be explicit, reproducible, and mathematically correct.

