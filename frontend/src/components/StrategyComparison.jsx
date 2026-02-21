import { useMemo } from 'react';
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
  Legend,
} from 'recharts';
import { analyzeStrategy, strategyPayoff } from './PayoffDiagram';

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
  return legs.map((l) => `${l.action === 'buy' ? 'Buy' : 'Sell'} ${l.type} $${l.strike}`).join(' / ');
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

export default function StrategyComparison({ slotA, slotB, currentPrice, onClear }) {
  const analysisA = useMemo(() => analyzeStrategy(slotA.legs, currentPrice), [slotA.legs, currentPrice]);
  const analysisB = useMemo(() => analyzeStrategy(slotB.legs, currentPrice), [slotB.legs, currentPrice]);

  if (!analysisA || !analysisB) return null;

  // Merge data into one array for overlaid chart
  const mergedData = useMemo(() => {
    const allPrices = new Set();
    analysisA.data.forEach((d) => allPrices.add(d.price));
    analysisB.data.forEach((d) => allPrices.add(d.price));
    const sorted = [...allPrices].sort((a, b) => a - b);

    const mapA = new Map(analysisA.data.map((d) => [d.price, d.pl]));
    const mapB = new Map(analysisB.data.map((d) => [d.price, d.pl]));

    return sorted.map((price) => ({
      price,
      plA: mapA.get(price) ?? null,
      plB: mapB.get(price) ?? null,
    }));
  }, [analysisA, analysisB]);

  const metrics = [
    {
      label: 'Max Profit',
      a: isFinite(analysisA.maxProfit) ? `$${fmt(analysisA.maxProfit)}` : 'Unlimited',
      b: isFinite(analysisB.maxProfit) ? `$${fmt(analysisB.maxProfit)}` : 'Unlimited',
    },
    {
      label: 'Max Loss',
      a: isFinite(analysisA.maxLoss) ? `$${fmt(analysisA.maxLoss)}` : 'Unlimited',
      b: isFinite(analysisB.maxLoss) ? `$${fmt(analysisB.maxLoss)}` : 'Unlimited',
    },
    {
      label: 'Breakevens',
      a: analysisA.breakevens.map((be) => `$${fmt(be)}`).join(', ') || '—',
      b: analysisB.breakevens.map((be) => `$${fmt(be)}`).join(', ') || '—',
    },
    {
      label: 'Net Premium',
      a: `${analysisA.netPremium >= 0 ? 'Credit' : 'Debit'} $${fmt(Math.abs(analysisA.netPremium))}`,
      b: `${analysisB.netPremium >= 0 ? 'Credit' : 'Debit'} $${fmt(Math.abs(analysisB.netPremium))}`,
    },
    {
      label: 'Risk / Reward',
      a: analysisA.riskReward != null ? `1 : ${analysisA.riskReward.toFixed(2)}` : '—',
      b: analysisB.riskReward != null ? `1 : ${analysisB.riskReward.toFixed(2)}` : '—',
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
