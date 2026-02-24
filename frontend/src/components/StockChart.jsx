import { useState, useEffect, useRef } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, ReferenceLine,
} from 'recharts';
import { getHistory } from '../api/client';

const PERIODS = [
  { label: '1D', period: '1d', interval: '5m' },
  { label: '1W', period: '5d', interval: '15m' },
  { label: '1M', period: '1mo', interval: '1d' },
  { label: '3M', period: '3mo', interval: '1d' },
  { label: 'YTD', period: 'ytd', interval: '1d' },
  { label: '1Y', period: '1y', interval: '1d' },
  { label: '3Y', period: '3y', interval: '1wk' },
  { label: '5Y', period: '5y', interval: '1wk' },
];

function formatDate(dateStr, periodLabel) {
  const d = new Date(dateStr);
  if (periodLabel === '1D' || periodLabel === '1W') {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  if (periodLabel === '1M' || periodLabel === '3M') {
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
  return d.toLocaleDateString([], { month: 'short', year: '2-digit' });
}

function formatTooltipDate(dateStr, periodLabel) {
  const d = new Date(dateStr);
  if (periodLabel === '1D' || periodLabel === '1W') {
    return d.toLocaleString([], {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

function ChartTooltip({ active, payload, periodLabel }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="payoff-tooltip">
      <div className="payoff-tooltip-row">
        <span className="payoff-tooltip-label">{formatTooltipDate(d.date, periodLabel)}</span>
      </div>
      <div className="payoff-tooltip-row">
        <span className="payoff-tooltip-label">Close</span>
        <span className="payoff-tooltip-value">${d.close.toFixed(2)}</span>
      </div>
      <div className="payoff-tooltip-row">
        <span className="payoff-tooltip-label">Open</span>
        <span className="payoff-tooltip-value">${d.open.toFixed(2)}</span>
      </div>
      <div className="payoff-tooltip-row">
        <span className="payoff-tooltip-label">High</span>
        <span className="payoff-tooltip-value">${d.high.toFixed(2)}</span>
      </div>
      <div className="payoff-tooltip-row">
        <span className="payoff-tooltip-label">Low</span>
        <span className="payoff-tooltip-value">${d.low.toFixed(2)}</span>
      </div>
      {d.change !== undefined && (
        <div className="payoff-tooltip-row">
          <span className="payoff-tooltip-label">Change</span>
          <span className={`payoff-tooltip-value ${d.change >= 0 ? 'text-green' : 'text-red'}`}>
            {d.change >= 0 ? '+' : ''}${d.change.toFixed(2)} ({d.changePct >= 0 ? '+' : ''}{d.changePct.toFixed(1)}%)
          </span>
        </div>
      )}
    </div>
  );
}

export default function StockChart({ symbol }) {
  const [periodLabel, setPeriodLabel] = useState('1Y');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);

  useEffect(() => {
    if (!symbol) return;
    const id = ++reqId.current;
    setLoading(true);
    const p = PERIODS.find((p) => p.label === periodLabel);
    getHistory(symbol, p.period, p.interval)
      .then((res) => {
        if (id !== reqId.current) return;
        const rows = (res.history || []).map((r, i, arr) => {
          const prev = i > 0 ? arr[i - 1].close : r.open;
          return {
            ...r,
            change: r.close - prev,
            changePct: prev ? ((r.close - prev) / prev) * 100 : 0,
          };
        });
        setData(rows);
      })
      .catch(() => { if (id === reqId.current) setData([]); })
      .finally(() => { if (id === reqId.current) setLoading(false); });
  }, [symbol, periodLabel]);

  const first = data[0]?.close;
  const last = data[data.length - 1]?.close;
  const isUp = last >= first;
  const color = isUp ? 'var(--accent-cyan)' : 'var(--accent-red)';
  const gradientId = isUp ? 'chartGradientUp' : 'chartGradientDown';

  const closes = data.map((d) => d.close);
  const minY = closes.length ? Math.min(...closes) : 0;
  const maxY = closes.length ? Math.max(...closes) : 0;
  const pad = (maxY - minY) * 0.05 || 1;

  // Thin out x-axis ticks
  const tickCount = 6;
  const step = data.length > tickCount ? Math.floor(data.length / tickCount) : 1;
  const ticks = data.filter((_, i) => i % step === 0).map((d) => d.date);

  return (
    <div className="stock-chart">
      <div className="chart-period-btns">
        {PERIODS.map((p) => (
          <button
            key={p.label}
            className={periodLabel === p.label ? 'active' : ''}
            onClick={() => setPeriodLabel(p.label)}
          >
            {p.label}
          </button>
        ))}
      </div>
      {loading ? (
        <div className="loading" style={{ height: 280 }}>
          <span className="spinner" />Loading chart...
        </div>
      ) : data.length === 0 ? (
        <div className="loading" style={{ height: 280 }}>No data available</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tickFormatter={(v) => formatDate(v, periodLabel)}
                ticks={ticks}
                tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[minY - pad, maxY + pad]}
                tickFormatter={(v) => `$${v.toFixed(0)}`}
                tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
                width={50}
              />
              <Tooltip content={<ChartTooltip periodLabel={periodLabel} />} />
              {first && (
                <ReferenceLine
                  y={first}
                  stroke="var(--text-muted)"
                  strokeDasharray="3 3"
                  strokeOpacity={0.4}
                />
              )}
              <Area
                type="monotone"
                dataKey="close"
                stroke={color}
                strokeWidth={1.5}
                fill={`url(#${gradientId})`}
                dot={false}
                activeDot={{ r: 3, fill: color, stroke: 'var(--bg-primary)', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
          <ResponsiveContainer width="100%" height={40}>
            <BarChart data={data} margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
              <XAxis dataKey="date" hide />
              <YAxis hide />
              <Bar dataKey="volume" fill="var(--text-muted)" opacity={0.2} radius={[1, 1, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
}
