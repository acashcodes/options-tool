import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { getOptionsAnalytics } from '../api/client';

export default function OptionsAnalytics({ symbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    setError('');
    getOptionsAnalytics(symbol)
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="loading"><span className="spinner" /> Loading analytics...</div>;
  if (error) return <div className="analytics-error">{error}</div>;
  if (!data) return null;

  return (
    <div className="options-analytics">
      <h3 className="section-title">Options Analytics</h3>

      <div className="analytics-grid">
        {/* Expected Moves */}
        {data.expected_moves && data.expected_moves.length > 0 && (
          <div className="analytics-card">
            <div className="analytics-card-label">Expected Moves</div>
            <div className="expected-moves-list">
              {data.expected_moves.map((em, i) => (
                <div key={i} className="expected-move-badge">
                  <span className="em-expiry">{em.dte}d</span>
                  <span className="em-pct">&plusmn;{em.expected_move_pct}%</span>
                  <span className="em-dollar">&plusmn;${em.expected_move_dollar}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Put/Call Flow */}
        {data.flow && (
          <div className="analytics-card">
            <div className="analytics-card-label">Put/Call Flow</div>
            <div className="flow-summary">
              <div className="flow-row">
                <span>Call Volume</span>
                <span className="flow-val">{(data.flow.total_call_volume || 0).toLocaleString()}</span>
              </div>
              <div className="flow-row">
                <span>Put Volume</span>
                <span className="flow-val">{(data.flow.total_put_volume || 0).toLocaleString()}</span>
              </div>
              <div className="flow-row">
                <span>P/C Ratio (Vol)</span>
                <span className={`flow-val ${data.flow.pc_ratio_volume > 1 ? 'color-red' : 'color-green'}`}>
                  {data.flow.pc_ratio_volume ?? '\u2014'}
                </span>
              </div>
              <div className="flow-row">
                <span>P/C Ratio (OI)</span>
                <span className={`flow-val ${data.flow.pc_ratio_oi > 1 ? 'color-red' : 'color-green'}`}>
                  {data.flow.pc_ratio_oi ?? '\u2014'}
                </span>
              </div>
            </div>
            {data.flow.unusual_activity && data.flow.unusual_activity.length > 0 && (
              <div className="unusual-activity">
                <div className="unusual-label">Unusual Activity</div>
                {data.flow.unusual_activity.slice(0, 5).map((ua, i) => (
                  <div key={i} className="unusual-row">
                    <span className={ua.type === 'call' ? 'color-green' : 'color-red'}>
                      {ua.type.toUpperCase()}
                    </span>
                    <span>${ua.strike} {ua.expiration}</span>
                    <span>Vol {ua.volume.toLocaleString()} ({ua.ratio}x OI)</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* IV Term Structure Chart */}
      {data.iv_term_structure && data.iv_term_structure.length > 1 && (
        <div className="analytics-chart-card">
          <div className="analytics-card-label">IV Term Structure</div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.iv_term_structure} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="dte" label={{ value: 'DTE', position: 'insideBottom', offset: -2, fontSize: 11 }} tick={{ fontSize: 11 }} stroke="rgba(255,255,255,0.3)" />
              <YAxis tick={{ fontSize: 11 }} stroke="rgba(255,255,255,0.3)" unit="%" />
              <Tooltip contentStyle={{ background: '#1a1a2e', border: '1px solid #2a2a3e', fontSize: 12 }} />
              <Line type="monotone" dataKey="atm_iv" stroke="#4fc3f7" strokeWidth={2} dot={{ fill: '#4fc3f7', r: 4 }} name="ATM IV" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Skew Chart */}
      {data.skew && data.skew.strikes && data.skew.strikes.length > 3 && (
        <div className="analytics-chart-card">
          <div className="analytics-card-label">
            IV Skew &mdash; {data.skew.expiration}
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart
              data={data.skew.strikes.map((s, i) => ({
                strike: s,
                call_iv: data.skew.call_iv[i],
                put_iv: data.skew.put_iv[i],
              }))}
              margin={{ top: 10, right: 20, bottom: 5, left: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="strike" tick={{ fontSize: 10 }} stroke="rgba(255,255,255,0.3)" />
              <YAxis tick={{ fontSize: 11 }} stroke="rgba(255,255,255,0.3)" unit="%" />
              <Tooltip contentStyle={{ background: '#1a1a2e', border: '1px solid #2a2a3e', fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="call_iv" stroke="#4fc3f7" strokeWidth={2} dot={false} name="Call IV" connectNulls />
              <Line type="monotone" dataKey="put_iv" stroke="#ff7043" strokeWidth={2} dot={false} name="Put IV" connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
