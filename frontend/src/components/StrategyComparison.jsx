import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
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

function legsSummary(legs) {
  return legs.map((l) => {
    if (l.instrument === 'stock') {
      return `${l.action === 'buy' ? 'Buy' : 'Sell'} ${l.quantity} Shares`;
    }
    return `${l.action === 'buy' ? 'Buy' : 'Sell'} ${l.type} $${l.strike}`;
  }).join(' / ');
}

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
    iv: leg.iv != null ? leg.iv / 100 : null,
    multiplier: 100,
    entry_price: leg.premium || 0,
    bid: leg.bid,
    ask: leg.ask,
  };
}

function buildPayload(legs, currentPrice, quote) {
  return {
    underlying: {
      price: currentPrice,
      dividend_yield: quote?.dividend_yield || 0,
    },
    legs: legs.map(toBackendLeg),
    days_forward: 0,
    curve_points: 200,
  };
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="payoff-tooltip">
      <div className="payoff-tooltip-row">
        <span className="payoff-tooltip-label">Stock Price</span>
        <span className="payoff-tooltip-value">${Number(label).toFixed(2)}</span>
      </div>
      {payload.map((p) => (
        <div className="payoff-tooltip-row" key={p.dataKey}>
          <span className="payoff-tooltip-label">{p.name}</span>
          <span className={`payoff-tooltip-value ${p.value >= 0 ? 'text-green' : 'text-red'}`}>
            {p.value >= 0 ? '+' : ''}${fmt(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function StrategyComparison({ slotA, slotB, currentPrice, quote, onClear }) {
  const [analysisA, setAnalysisA] = useState(null);
  const [analysisB, setAnalysisB] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchBoth = useCallback(async () => {
    if (!slotA?.legs?.length || !slotB?.legs?.length || !currentPrice) return;
    setLoading(true);
    setError(null);
    try {
      const [dataA, dataB] = await Promise.all([
        analyzeStrategyAPI(buildPayload(slotA.legs, currentPrice, quote)),
        analyzeStrategyAPI(buildPayload(slotB.legs, currentPrice, quote)),
      ]);
      setAnalysisA(dataA);
      setAnalysisB(dataB);
    } catch (err) {
      setError(err.message);
      setAnalysisA(null);
      setAnalysisB(null);
    } finally {
      setLoading(false);
    }
  }, [slotA, slotB, currentPrice, quote]);

  useEffect(() => {
    fetchBoth();
  }, [fetchBoth]);

  if (loading) {
    return (
      <div className="comparison-section">
        <h2>Strategy Comparison</h2>
        <div className="loading"><span className="spinner" /> Computing comparison...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="comparison-section">
        <h2>Strategy Comparison</h2>
        <div className="error-msg">{error}</div>
      </div>
    );
  }

  if (!analysisA || !analysisB) return null;

  const curveA = analysisA.curves?.expiration || [];
  const curveB = analysisB.curves?.expiration || [];

  const mergedData = useMemo(() => {
    const mapA = new Map(curveA.map((d) => [d.price, d.pl]));
    const mapB = new Map(curveB.map((d) => [d.price, d.pl]));
    const allPrices = new Set([...mapA.keys(), ...mapB.keys()]);
    const sorted = [...allPrices].sort((a, b) => a - b);
    return sorted.map((price) => ({
      price,
      plA: mapA.get(price) ?? null,
      plB: mapB.get(price) ?? null,
    }));
  }, [curveA, curveB]);

  const metrics = [
    {
      label: 'Max Profit',
      a: analysisA.max_profit != null ? `$${fmt(analysisA.max_profit)}` : 'Unlimited',
      b: analysisB.max_profit != null ? `$${fmt(analysisB.max_profit)}` : 'Unlimited',
    },
    {
      label: 'Max Loss',
      a: analysisA.max_loss != null ? `$${fmt(analysisA.max_loss)}` : 'Unlimited',
      b: analysisB.max_loss != null ? `$${fmt(analysisB.max_loss)}` : 'Unlimited',
    },
    {
      label: 'Breakevens',
      a: (analysisA.breakevens || []).map((be) => `$${fmt(be)}`).join(', ') || '—',
      b: (analysisB.breakevens || []).map((be) => `$${fmt(be)}`).join(', ') || '—',
    },
    {
      label: 'Net Premium',
      a: `${analysisA.net_premium >= 0 ? 'Credit' : 'Debit'} $${fmt(Math.abs(analysisA.net_premium))}`,
      b: `${analysisB.net_premium >= 0 ? 'Credit' : 'Debit'} $${fmt(Math.abs(analysisB.net_premium))}`,
    },
    {
      label: 'Capital Required',
      a: `$${fmt(analysisA.capital_required)}`,
      b: `$${fmt(analysisB.capital_required)}`,
    },
    {
      label: 'Risk / Reward',
      a: analysisA.risk_reward != null ? `1 : ${analysisA.risk_reward.toFixed(2)}` : '—',
      b: analysisB.risk_reward != null ? `1 : ${analysisB.risk_reward.toFixed(2)}` : '—',
    },
    {
      label: 'Prob. of Profit',
      a: analysisA.pop?.value != null ? `${analysisA.pop.value.toFixed(1)}%` : '—',
      b: analysisB.pop?.value != null ? `${analysisB.pop.value.toFixed(1)}%` : '—',
    },
  ];

  return (
    <div className="comparison-section">
      <div className="comparison-header">
        <h2>Strategy Comparison</h2>
        <button className="btn-ghost" onClick={onClear}>Clear Comparison</button>
      </div>

      <div className="comparison-labels">
        <div className="comparison-label label-a">
          <span className="comparison-dot dot-a" />
          <span className="comparison-slot">Strategy A</span>
          <span className="comparison-desc">{legsSummary(slotA.legs)}</span>
        </div>
        <div className="comparison-label label-b">
          <span className="comparison-dot dot-b" />
          <span className="comparison-slot">Strategy B</span>
          <span className="comparison-desc">{legsSummary(slotB.legs)}</span>
        </div>
      </div>

      <div className="comparison-chart-container">
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={mergedData} margin={{ top: 10, right: 30, left: 10, bottom: 30 }}>
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
            <ReferenceLine x={currentPrice} stroke="#5a5a72" strokeDasharray="6 4" />
            <Line type="monotone" dataKey="plA" name="Strategy A" stroke="#00d4aa" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey="plB" name="Strategy B" stroke="#3498db" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="comparison-table-wrapper">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th><span className="comparison-dot dot-a" /> Strategy A</th>
              <th><span className="comparison-dot dot-b" /> Strategy B</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.label}>
                <td className="metric-name">{m.label}</td>
                <td>{m.a}</td>
                <td>{m.b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
