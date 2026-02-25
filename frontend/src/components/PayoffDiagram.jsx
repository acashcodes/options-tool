import { useEffect, useState, useCallback } from 'react';
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
import { analyzeStrategy as analyzeStrategyAPI } from '../api/client';

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

// Convert frontend leg to backend StrategyLeg schema
function toBackendLeg(leg) {
  if (leg.instrument === 'stock') {
    return {
      instrument: 'stock',
      action: leg.action,
      quantity: leg.quantity,
      entry_price: leg.entry_price || leg.premium || 0,
    };
  }
  return {
    instrument: 'option',
    option_type: leg.type === 'Call' ? 'call' : 'put',
    action: leg.action,
    quantity: leg.quantity,
    strike: leg.strike,
    expiration: leg.expiration,
    iv: leg.iv != null ? leg.iv / 100 : null, // UI stores percent, backend wants decimal
    multiplier: 100,
    entry_price: leg.premium || 0,
    bid: leg.bid,
    ask: leg.ask,
  };
}

// Build the full payload for the backend
function buildPayload(legs, currentPrice, daysForward = 0, quote = null) {
  return {
    underlying: {
      price: currentPrice,
      dividend_yield: quote?.dividend_yield || 0,
    },
    legs: legs.map(toBackendLeg),
    days_forward: daysForward,
    curve_points: 200,
  };
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

// For StrategyComparison: simple expiration payoff (kept as fallback, not for metrics)
export function strategyPayoff(legs, stockPrice) {
  return legs.reduce((total, leg) => {
    if (leg.instrument === 'stock') {
      const q = leg.action === 'buy' ? leg.quantity : -leg.quantity;
      return total + q * (stockPrice - (leg.entry_price || leg.premium || 0));
    }
    const { type, strike, action, quantity, premium } = leg;
    const multiplier = action === 'buy' ? 1 : -1;
    const intrinsic = type === 'Call'
      ? Math.max(0, stockPrice - strike)
      : Math.max(0, strike - stockPrice);
    return total + (intrinsic * multiplier - premium * (action === 'buy' ? 1 : -1)) * 100 * quantity;
  }, 0);
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

export default function PayoffDiagram({ legs, currentPrice, title, quote }) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const maxDTE = getMaxDTE(legs);
  const [dte, setDte] = useState(Math.min(maxDTE, getMaxDTE(legs)));

  const effectiveDTE = Math.min(dte, maxDTE);

  const fetchAnalysis = useCallback(async () => {
    if (!legs.length || !currentPrice) return;
    setLoading(true);
    setError(null);
    try {
      const payload = buildPayload(legs, currentPrice, effectiveDTE, quote);
      const data = await analyzeStrategyAPI(payload);
      setAnalysis(data);
    } catch (err) {
      setError(err.message);
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }, [legs, currentPrice, effectiveDTE, quote]);

  useEffect(() => {
    fetchAnalysis();
  }, [fetchAnalysis]);

  if (loading) {
    return (
      <div className="payoff-section">
        <h2>{title || 'Payoff Analysis'}</h2>
        <div className="loading"><span className="spinner" /> Computing analysis...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="payoff-section">
        <h2>{title || 'Payoff Analysis'}</h2>
        <div className="error-msg">{error}</div>
      </div>
    );
  }

  if (!analysis) return null;

  const {
    max_profit: maxProfit,
    max_loss: maxLoss,
    breakevens = [],
    net_premium: netPremium,
    risk_reward: riskReward,
    capital_required: totalCapital,
    requires_margin: requiresMargin,
    pop,
  } = analysis;

  // Merge expiration and MTM curves
  const expCurve = analysis.curves?.expiration || [];
  const mtmCurve = analysis.curves?.mtm || [];
  const chartData = expCurve.map((d, i) => ({
    price: d.price,
    pl: d.pl,
    profit: d.pl >= 0 ? d.pl : 0,
    loss: d.pl < 0 ? d.pl : 0,
    preExpPL: effectiveDTE > 0 && mtmCurve[i] ? mtmCurve[i].pl : undefined,
  }));

  const maxProfitPct = maxProfit != null ? pctReturn(maxProfit, totalCapital) : null;
  const maxLossPct = maxLoss != null ? pctReturn(maxLoss, totalCapital) : null;
  const probOfProfit = pop?.value ?? null;

  // Compute P&L at current price from expiration curve
  let plAtCurrent = null;
  if (expCurve.length > 0) {
    let closest = expCurve[0];
    for (const pt of expCurve) {
      if (Math.abs(pt.price - currentPrice) < Math.abs(closest.price - currentPrice)) {
        closest = pt;
      }
    }
    plAtCurrent = closest.pl;
  }

  return (
    <div className="payoff-section">
      <h2>{title || 'Payoff Analysis'}</h2>

      {analysis.assumptions_used && (
        <div className="assumptions-badge">
          r={((analysis.assumptions_used.risk_free_rate || 0) * 100).toFixed(2)}%
          {analysis.assumptions_used.dividend_yield > 0 && ` q=${((analysis.assumptions_used.dividend_yield) * 100).toFixed(2)}%`}
          {' '}BSM
        </div>
      )}

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
              <CartesianGrid stroke="#e0e0e8" strokeDasharray="3 3" />
              <XAxis
                dataKey="price"
                type="number"
                domain={['dataMin', 'dataMax']}
                tick={{ fill: '#6a6a7a', fontSize: 11 }}
                tickFormatter={(v) => `$${v.toFixed(0)}`}
                stroke="#c5cad6"
              >
                <Label value="Stock Price at Expiration" position="bottom" offset={10} fill="#6a6a7a" fontSize={11} />
              </XAxis>
              <YAxis
                tick={{ fill: '#6a6a7a', fontSize: 11 }}
                tickFormatter={(v) => fmtCompact(v)}
                stroke="#c5cad6"
              >
                <Label value="Profit / Loss ($)" angle={-90} position="insideLeft" offset={0} fill="#6a6a7a" fontSize={11} style={{ textAnchor: 'middle' }} />
              </YAxis>
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#b0b0c0" strokeWidth={1} />
              <ReferenceLine
                x={currentPrice}
                stroke="#9a9ab0"
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
                  stroke="#2563eb"
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
              {maxProfit != null ? `$${fmt(maxProfit)}` : 'Unlimited'}
            </span>
            {maxProfit != null && maxProfitPct && (
              <span className="stat-pct text-green">+{maxProfitPct}% return</span>
            )}
          </div>
          <div className="payoff-stat-card loss-card">
            <span className="stat-label">Max Loss</span>
            <span className="stat-value text-red">
              {maxLoss != null ? `$${fmt(maxLoss)}` : 'Unlimited'}
            </span>
            {maxLoss != null && maxLossPct && (
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
            <span className="stat-label">Capital Required</span>
            <span className="stat-value">
              ${fmt(totalCapital)}
            </span>
            {requiresMargin && (
              <span className="stat-pct" style={{ color: '#ffa502' }}>
                Margin required
              </span>
            )}
          </div>
          <div className="payoff-stat-card">
            <span className="stat-label">Net Premium</span>
            <span className={`stat-value ${netPremium >= 0 ? 'text-green' : 'text-red'}`}>
              {netPremium >= 0 ? 'Credit ' : 'Debit '}${fmt(Math.abs(netPremium))}
            </span>
          </div>
          <div className="payoff-stat-card">
            <span className="stat-label">Probability of Profit</span>
            <span className={`stat-value ${probOfProfit != null && probOfProfit >= 50 ? 'text-green' : 'text-red'}`}>
              {probOfProfit != null ? `${probOfProfit.toFixed(1)}%` : '—'}
            </span>
            {probOfProfit != null && (
              <>
                <div className="range-bar" style={{ marginTop: 4 }}>
                  <div
                    className={`range-bar-fill ${probOfProfit >= 50 ? 'fill-cyan' : 'fill-red'}`}
                    style={{ width: `${probOfProfit}%` }}
                  />
                </div>
                <span className="stat-pct" style={{ color: 'var(--text-muted)', fontSize: 10 }}>
                  Model-based (log-normal)
                </span>
              </>
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
            <span className={`stat-value ${plAtCurrent != null && plAtCurrent >= 0 ? 'text-green' : 'text-red'}`}>
              {plAtCurrent != null ? `$${fmt(plAtCurrent)}` : '—'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
