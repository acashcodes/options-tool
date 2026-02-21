import { useMemo, useState } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Label,
} from 'recharts';

function fmt(n) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtCompact(n) {
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function pctReturn(pl, capital) {
  if (!capital || capital === 0) return null;
  return ((pl / Math.abs(capital)) * 100).toFixed(1);
}

// ---------------------------------------------------------------------------
// Client-side Black-Scholes for pre-expiration curves
// ---------------------------------------------------------------------------

// Standard normal CDF approximation (Abramowitz & Stegun)
function normCDF(x) {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
  const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  x = Math.abs(x) / Math.SQRT2;
  const t = 1.0 / (1.0 + p * x);
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return 0.5 * (1.0 + sign * y);
}

function bsPrice(S, K, t, r, sigma, optType) {
  if (t <= 0) {
    return optType === 'call' ? Math.max(0, S - K) : Math.max(0, K - S);
  }
  if (sigma <= 0) {
    const fwd = S * Math.exp(r * t);
    return optType === 'call'
      ? Math.max(0, fwd - K) * Math.exp(-r * t)
      : Math.max(0, K - fwd) * Math.exp(-r * t);
  }
  const sqrtT = Math.sqrt(t);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * t) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  if (optType === 'call') {
    return S * normCDF(d1) - K * Math.exp(-r * t) * normCDF(d2);
  }
  return K * Math.exp(-r * t) * normCDF(-d2) - S * normCDF(-d1);
}

// ---------------------------------------------------------------------------
// Payoff functions
// ---------------------------------------------------------------------------

function legPayoff(leg, stockPrice) {
  const { type, strike, action, quantity, premium } = leg;
  const multiplier = action === 'buy' ? 1 : -1;
  let intrinsic = 0;
  if (type === 'Call') {
    intrinsic = Math.max(0, stockPrice - strike);
  } else {
    intrinsic = Math.max(0, strike - stockPrice);
  }
  const payoffPerContract = (intrinsic * multiplier - premium * (action === 'buy' ? 1 : -1)) * 100;
  return payoffPerContract * quantity;
}

export function strategyPayoff(legs, stockPrice) {
  return legs.reduce((total, leg) => total + legPayoff(leg, stockPrice), 0);
}

// Pre-expiration P&L: BS theoretical value minus entry cost
function legPreExpPL(leg, stockPrice, tYears, r) {
  const { type, strike, action, quantity, premium, iv } = leg;
  const optType = type === 'Call' ? 'call' : 'put';
  const sigma = iv != null ? iv / 100 : 0.30; // fallback to 30% if no IV
  const currentValue = bsPrice(stockPrice, strike, tYears, r, sigma, optType);
  const multiplier = action === 'buy' ? 1 : -1;
  const entryPremium = premium * (action === 'buy' ? 1 : -1);
  const plPerContract = (currentValue * multiplier - entryPremium) * 100;
  return plPerContract * quantity;
}

function strategyPreExpPL(legs, stockPrice, tYears, r = 0.045) {
  return legs.reduce((total, leg) => total + legPreExpPL(leg, stockPrice, tYears, r), 0);
}

export function findBreakevens(legs, priceMin, priceMax, steps = 10000) {
  const breakevens = [];
  const step = (priceMax - priceMin) / steps;
  let prevPL = strategyPayoff(legs, priceMin);
  for (let i = 1; i <= steps; i++) {
    const price = priceMin + step * i;
    const pl = strategyPayoff(legs, price);
    if ((prevPL < 0 && pl >= 0) || (prevPL >= 0 && pl < 0)) {
      const ratio = Math.abs(prevPL) / (Math.abs(prevPL) + Math.abs(pl));
      breakevens.push(+(price - step + step * ratio).toFixed(2));
    }
    prevPL = pl;
  }
  return breakevens;
}

// Probability that stock finishes above a given price (log-normal model)
function probAbove(S, target, tYears, sigma, r = 0.045) {
  if (tYears <= 0) return S > target ? 1 : 0;
  if (sigma <= 0) return S * Math.exp(r * tYears) > target ? 1 : 0;
  const d2 = (Math.log(S / target) + (r - 0.5 * sigma * sigma) * tYears) / (sigma * Math.sqrt(tYears));
  return normCDF(d2);
}

// Estimate P(profit) by checking probability of landing in profitable regions
function estimateProbOfProfit(legs, currentPrice, breakevens, priceMin, priceMax) {
  if (!legs.length || !breakevens.length) return null;

  // Get average IV and DTE across legs
  let totalIV = 0, ivCount = 0, maxDTE = 30;
  for (const leg of legs) {
    if (leg.iv != null) { totalIV += leg.iv; ivCount++; }
    if (leg.expiration) {
      const exp = new Date(leg.expiration + 'T00:00:00');
      const now = new Date(); now.setHours(0, 0, 0, 0);
      const days = Math.round((exp - now) / 86400000);
      if (days > maxDTE) maxDTE = days;
    }
  }
  const sigma = ivCount > 0 ? (totalIV / ivCount) / 100 : 0.30;
  const tYears = maxDTE / 365;

  // Check profitability at boundaries and breakevens to identify profit regions
  const sortedBE = [...breakevens].sort((a, b) => a - b);
  const testPoints = [0.01, ...sortedBE, priceMax * 2];

  let profitProb = 0;
  // Test midpoint between each adjacent pair of test points
  for (let i = 0; i < testPoints.length - 1; i++) {
    const lo = testPoints[i];
    const hi = testPoints[i + 1];
    const mid = (lo + hi) / 2;
    const pl = strategyPayoff(legs, mid);
    if (pl > 0) {
      // Region [lo, hi] is profitable
      const pHi = i + 1 < testPoints.length - 1 ? probAbove(currentPrice, lo, tYears, sigma) - probAbove(currentPrice, hi, tYears, sigma) : probAbove(currentPrice, lo, tYears, sigma);
      profitProb += Math.max(0, pHi);
    }
  }

  return Math.max(0, Math.min(100, profitProb * 100));
}

export function analyzeStrategy(legs, currentPrice) {
  if (!legs.length || !currentPrice) return null;

  const strikes = legs.map((l) => l.strike);
  const minStrike = Math.min(...strikes);
  const maxStrike = Math.max(...strikes);
  const spread = maxStrike - minStrike || currentPrice * 0.2;
  const padding = Math.max(spread * 1.5, currentPrice * 0.15);
  const priceMin = Math.max(0, minStrike - padding);
  const priceMax = maxStrike + padding;

  const numPoints = 200;
  const step = (priceMax - priceMin) / numPoints;
  const data = [];
  let maxProfit = -Infinity;
  let maxLoss = Infinity;

  for (let i = 0; i <= numPoints; i++) {
    const price = priceMin + step * i;
    const pl = strategyPayoff(legs, price);
    maxProfit = Math.max(maxProfit, pl);
    maxLoss = Math.min(maxLoss, pl);
    data.push({
      price: +price.toFixed(2),
      pl: +pl.toFixed(2),
      profit: pl >= 0 ? +pl.toFixed(2) : 0,
      loss: pl < 0 ? +pl.toFixed(2) : 0,
    });
  }

  // Structural unlimited detection:
  // Net long calls > 0 → unlimited upside profit. Net short calls > 0 → unlimited upside loss.
  // (Puts are always bounded since stock can't go below 0.)
  const netCallQty = legs
    .filter(l => l.type === 'Call')
    .reduce((sum, l) => sum + (l.action === 'buy' ? l.quantity : -l.quantity), 0);
  if (netCallQty > 0) maxProfit = Infinity;
  if (netCallQty < 0) maxLoss = -Infinity;

  // Also check P&L at extremes to tighten finite bounds
  const farOutPL = strategyPayoff(legs, priceMax * 3);
  const farDownPL = strategyPayoff(legs, 0.01);
  maxProfit = Math.max(maxProfit, farOutPL, farDownPL);
  maxLoss = Math.min(maxLoss, farOutPL, farDownPL);

  const breakevens = findBreakevens(legs, priceMin, priceMax);

  const netPremium = legs.reduce((sum, leg) => {
    const cost = (leg.premium || 0) * leg.quantity * 100;
    return sum + (leg.action === 'buy' ? -cost : cost);
  }, 0);

  const totalCapital = Math.abs(netPremium);

  let riskReward = null;
  if (isFinite(maxProfit) && isFinite(maxLoss) && maxLoss !== 0) {
    riskReward = Math.abs(maxProfit / maxLoss);
  }

  const probOfProfit = estimateProbOfProfit(legs, currentPrice, breakevens, priceMin, priceMax);

  return { data, maxProfit, maxLoss, breakevens, netPremium, riskReward, totalCapital, priceMin, priceMax, probOfProfit };
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const pl = payload.find((p) => p.dataKey === 'pl')?.value;
  const preExp = payload.find((p) => p.dataKey === 'preExpPL')?.value;
  return (
    <div className="payoff-tooltip">
      <div className="payoff-tooltip-row">
        <span className="payoff-tooltip-label">Stock Price</span>
        <span className="payoff-tooltip-value">${Number(label).toFixed(2)}</span>
      </div>
      {pl != null && (
        <div className="payoff-tooltip-row">
          <span className="payoff-tooltip-label">At Expiry</span>
          <span className={`payoff-tooltip-value ${pl >= 0 ? 'text-green' : 'text-red'}`}>
            {pl >= 0 ? '+' : ''}${fmt(pl)}
          </span>
        </div>
      )}
      {preExp != null && (
        <div className="payoff-tooltip-row">
          <span className="payoff-tooltip-label">Current Est.</span>
          <span className={`payoff-tooltip-value ${preExp >= 0 ? 'text-green' : 'text-red'}`}>
            {preExp >= 0 ? '+' : ''}${fmt(preExp)}
          </span>
        </div>
      )}
    </div>
  );
}

// Compute max DTE from leg expirations
function getMaxDTE(legs) {
  let max = 30;
  for (const leg of legs) {
    if (leg.expiration) {
      const exp = new Date(leg.expiration + 'T00:00:00');
      const now = new Date();
      now.setHours(0, 0, 0, 0);
      const days = Math.round((exp - now) / 86400000);
      if (days > max) max = days;
    }
  }
  return max;
}

export default function PayoffDiagram({ legs, currentPrice, title }) {
  const analysis = useMemo(() => analyzeStrategy(legs, currentPrice), [legs, currentPrice]);
  const maxDTE = useMemo(() => getMaxDTE(legs), [legs]);
  const [dte, setDte] = useState(() => Math.min(maxDTE, getMaxDTE(legs)));

  // Re-sync if legs change and DTE exceeds new max
  const effectiveDTE = Math.min(dte, maxDTE);

  // Compute pre-expiration curve data
  const chartData = useMemo(() => {
    if (!analysis) return [];
    const tYears = effectiveDTE / 365;
    return analysis.data.map((d) => {
      const preExpPL = effectiveDTE > 0
        ? +strategyPreExpPL(legs, d.price, tYears).toFixed(2)
        : d.pl;
      return { ...d, preExpPL };
    });
  }, [analysis, legs, effectiveDTE]);

  if (!analysis) return null;

  const { maxProfit, maxLoss, breakevens, netPremium, riskReward, totalCapital, probOfProfit } = analysis;

  const maxProfitPct = pctReturn(maxProfit, totalCapital);
  const maxLossPct = pctReturn(maxLoss, totalCapital);

  return (
    <div className="payoff-section">
      <h2>{title || 'Payoff Analysis'}</h2>

      <div className="payoff-layout">
        <div className="payoff-chart-container">
          <div className="payoff-chart-header">
            <div className="payoff-chart-title">Profit & Loss at Expiration</div>
            <div className="dte-slider">
              <label>DTE: <strong>{effectiveDTE}d</strong></label>
              <input
                type="range"
                min={0}
                max={maxDTE}
                step={1}
                value={effectiveDTE}
                onChange={(e) => setDte(Number(e.target.value))}
              />
              <div className="dte-labels">
                <span>Expiry</span>
                <span>{maxDTE}d</span>
              </div>
            </div>
          </div>
          <div className="payoff-legend">
            <span className="legend-item"><span className="legend-line legend-expiry" /> At Expiry</span>
            {effectiveDTE > 0 && (
              <span className="legend-item"><span className="legend-line legend-preexp" /> {effectiveDTE}d Before Expiry</span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 30 }}>
              <defs>
                <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00d4aa" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00d4aa" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff4757" stopOpacity={0} />
                  <stop offset="100%" stopColor="#ff4757" stopOpacity={0.3} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1a1a2e" strokeDasharray="3 3" />
              <XAxis
                dataKey="price"
                type="number"
                domain={['dataMin', 'dataMax']}
                tick={{ fill: '#5a5a72', fontSize: 11 }}
                tickFormatter={(v) => `$${v.toFixed(0)}`}
                stroke="#2a2a3e"
              >
                <Label value="Stock Price at Expiration" position="bottom" offset={10} fill="#5a5a72" fontSize={11} />
              </XAxis>
              <YAxis
                tick={{ fill: '#5a5a72', fontSize: 11 }}
                tickFormatter={(v) => fmtCompact(v)}
                stroke="#2a2a3e"
              >
                <Label value="Profit / Loss ($)" angle={-90} position="insideLeft" offset={0} fill="#5a5a72" fontSize={11} style={{ textAnchor: 'middle' }} />
              </YAxis>
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#3a3a52" strokeWidth={1} />
              <ReferenceLine
                x={currentPrice}
                stroke="#5a5a72"
                strokeDasharray="6 4"
                label={{
                  value: `Current: $${currentPrice.toFixed(2)}`,
                  position: 'top',
                  fill: '#8888a0',
                  fontSize: 11,
                }}
              />
              {breakevens.map((be, i) => (
                <ReferenceLine
                  key={`be-${i}`}
                  x={be}
                  stroke="#ffa502"
                  strokeDasharray="4 4"
                  strokeWidth={1}
                  label={{
                    value: `BE: $${be.toFixed(2)}`,
                    position: 'insideTopRight',
                    fill: '#ffa502',
                    fontSize: 10,
                  }}
                />
              ))}
              <Area type="monotone" dataKey="profit" fill="url(#profitGrad)" stroke="none" isAnimationActive={false} />
              <Area type="monotone" dataKey="loss" fill="url(#lossGrad)" stroke="none" isAnimationActive={false} />
              <Line type="monotone" dataKey="pl" stroke="#00d4aa" strokeWidth={2} dot={false} isAnimationActive={false} />
              {effectiveDTE > 0 && (
                <Line
                  type="monotone"
                  dataKey="preExpPL"
                  stroke="#3498db"
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  dot={false}
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="payoff-stats">
          <div className="payoff-stat-card profit-card">
            <span className="stat-label">Max Profit</span>
            <span className="stat-value text-green">
              {isFinite(maxProfit) ? `$${fmt(maxProfit)}` : 'Unlimited'}
            </span>
            {isFinite(maxProfit) && maxProfitPct && (
              <span className="stat-pct text-green">+{maxProfitPct}% return</span>
            )}
          </div>
          <div className="payoff-stat-card loss-card">
            <span className="stat-label">Max Loss</span>
            <span className="stat-value text-red">
              {isFinite(maxLoss) ? `$${fmt(maxLoss)}` : 'Unlimited'}
            </span>
            {isFinite(maxLoss) && maxLossPct && (
              <span className="stat-pct text-red">{maxLossPct}% return</span>
            )}
          </div>
          <div className="payoff-stat-card">
            <span className="stat-label">Breakeven{breakevens.length > 1 ? 's' : ''}</span>
            <span className="stat-value">
              {breakevens.length > 0
                ? breakevens.map((be) => `$${fmt(be)}`).join(', ')
                : '—'}
            </span>
            {breakevens.length > 0 && (
              <span className="stat-pct" style={{ color: 'var(--text-muted)' }}>
                {breakevens.map((be) => {
                  const pct = (((be - currentPrice) / currentPrice) * 100).toFixed(1);
                  return `${pct > 0 ? '+' : ''}${pct}%`;
                }).join(', ')} from current
              </span>
            )}
          </div>
          <div className="payoff-stat-card">
            <span className="stat-label">Net Premium</span>
            <span className={`stat-value ${netPremium >= 0 ? 'text-green' : 'text-red'}`}>
              {netPremium >= 0 ? 'Credit ' : 'Debit '}${fmt(Math.abs(netPremium))}
            </span>
            <span className="stat-pct" style={{ color: 'var(--text-muted)' }}>
              ${fmt(Math.abs(netPremium) / 100)} per share
            </span>
          </div>
          <div className="payoff-stat-card">
            <span className="stat-label">Probability of Profit</span>
            <span className={`stat-value ${probOfProfit != null && probOfProfit >= 50 ? 'text-green' : 'text-red'}`}>
              {probOfProfit != null ? `${probOfProfit.toFixed(1)}%` : '—'}
            </span>
            {probOfProfit != null && (
              <div className="range-bar" style={{ marginTop: 4 }}>
                <div
                  className={`range-bar-fill ${probOfProfit >= 50 ? 'fill-cyan' : 'fill-red'}`}
                  style={{ width: `${probOfProfit}%` }}
                />
              </div>
            )}
          </div>
          <div className="payoff-stat-card">
            <span className="stat-label">Risk / Reward</span>
            <span className="stat-value">
              {riskReward != null ? `1 : ${riskReward.toFixed(2)}` : '—'}
            </span>
          </div>
          <div className="payoff-stat-card">
            <span className="stat-label">P&L at Current Price</span>
            <span className={`stat-value ${strategyPayoff(legs, currentPrice) >= 0 ? 'text-green' : 'text-red'}`}>
              ${fmt(strategyPayoff(legs, currentPrice))}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
