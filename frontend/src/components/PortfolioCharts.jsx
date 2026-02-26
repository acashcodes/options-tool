import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const COLORS = [
  '#00d4aa', '#2563eb', '#8b5cf6', '#ffa502', '#ff4757',
  '#06b6d4', '#a855f7', '#10b981', '#f59e0b', '#ef4444',
];

export default function PortfolioCharts({ concentration, sectorBreakdown }) {
  const pieData = (concentration || [])
    .filter(c => c.weight > 0)
    .map(c => ({ name: c.ticker, value: c.weight }));

  const barData = Object.entries(sectorBreakdown || {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  if (pieData.length === 0 && barData.length === 0) return null;

  return (
    <div className="portfolio-charts">
      {pieData.length > 0 && (
        <div className="chart-card">
          <h3>Concentration</h3>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={95}
                  dataKey="value"
                  paddingAngle={2}
                  stroke="none"
                >
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.[0]) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="chart-tooltip">
                        <span className="chart-tooltip-label">{d.name}</span>
                        <span className="chart-tooltip-value">{d.value.toFixed(1)}%</span>
                      </div>
                    );
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="chart-legend">
              {pieData.map((d, i) => (
                <div key={d.name} className="legend-chip">
                  <span className="legend-dot" style={{ background: COLORS[i % COLORS.length] }} />
                  <span className="legend-label">{d.name}</span>
                  <span className="legend-pct">{d.value.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {barData.length > 0 && (
        <div className="chart-card">
          <h3>Sector Exposure</h3>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={barData} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
                <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fill: '#8888a0', fontSize: 10 }} />
                <YAxis type="category" dataKey="name" width={100} tick={{ fill: '#e8e8f0', fontSize: 11 }} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={18}>
                  {barData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.[0]) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="chart-tooltip">
                        <span className="chart-tooltip-label">{d.name}</span>
                        <span className="chart-tooltip-value">{d.value.toFixed(1)}%</span>
                      </div>
                    );
                  }}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
