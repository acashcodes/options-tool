import { useState, useEffect } from 'react';
import { getPortfolioRisk } from '../api/client';

function fmt(n) {
  if (n == null) return '\u2014';
  return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function fmtDollar(v) {
  if (v == null) return '\u2014';
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : v > 0 ? '+' : '';
  return `${sign}$${abs.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function corrColor(corr) {
  const abs = Math.abs(corr);
  if (abs >= 0.8) return 'text-red';
  if (abs >= 0.5) return 'text-yellow';
  return 'text-green';
}

export default function RiskPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPortfolioRisk()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) return (
    <div className="risk-panel">
      <h3>Risk Analysis</h3>
      <div className="loading"><span className="spinner" /> Loading risk metrics...</div>
    </div>
  );

  if (error) return (
    <div className="risk-panel">
      <h3>Risk Analysis</h3>
      <div className="error-msg">{error}</div>
    </div>
  );

  if (!data) return null;

  const { correlations = [], betas = {}, portfolio_beta, stress_tests = [] } = data;
  const hasBetas = Object.keys(betas).length > 0;
  const hasCorrelations = correlations.length > 0;
  const hasStress = stress_tests.length > 0;

  if (!hasBetas && !hasCorrelations && !hasStress) {
    return (
      <div className="risk-panel">
        <h3>Risk Analysis</h3>
        <p className="risk-empty">Add positions to see risk metrics.</p>
      </div>
    );
  }

  return (
    <div className="risk-panel">
      <h3>Risk Analysis</h3>

      <div className="risk-grid">
        {/* Portfolio Beta */}
        {portfolio_beta != null && (
          <div className="risk-card">
            <span className="risk-card-label">Portfolio Beta</span>
            <span className="risk-card-value">{fmt(portfolio_beta)}</span>
            <span className="risk-card-sub">vs SPY (6mo realized)</span>
          </div>
        )}

        {/* Per-ticker betas */}
        {hasBetas && (
          <div className="risk-card risk-card-wide">
            <span className="risk-card-label">Realized Betas</span>
            <div className="risk-beta-list">
              {Object.entries(betas)
                .filter(([t]) => t !== 'SPY')
                .sort((a, b) => Math.abs(b[1] || 0) - Math.abs(a[1] || 0))
                .slice(0, 8)
                .map(([ticker, beta]) => (
                  <div key={ticker} className="risk-beta-item">
                    <span className="risk-beta-ticker">{ticker}</span>
                    <span className="risk-beta-val">{beta != null ? fmt(beta) : '\u2014'}</span>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Top Correlations */}
        {hasCorrelations && (
          <div className="risk-card risk-card-wide">
            <span className="risk-card-label">Top Correlations</span>
            <div className="risk-corr-list">
              {correlations.slice(0, 5).map((pair, i) => (
                <div key={i} className="risk-corr-item">
                  <span className="risk-corr-pair">{pair.ticker_a} / {pair.ticker_b}</span>
                  <span className={`risk-corr-val ${corrColor(pair.correlation)}`}>
                    {pair.correlation.toFixed(2)}
                  </span>
                  {pair.high_correlation && <span className="risk-flag">High</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Stress Tests */}
        {hasStress && (
          <div className="risk-card risk-card-wide">
            <span className="risk-card-label">Stress Test (Market Move)</span>
            <div className="risk-stress-grid">
              {stress_tests.map((st, i) => (
                <div key={i} className="risk-stress-item">
                  <span className={`risk-stress-move ${st.move_pct >= 0 ? 'text-green' : 'text-red'}`}>
                    {st.move_pct >= 0 ? '+' : ''}{st.move_pct}%
                  </span>
                  <span className={`risk-stress-pnl ${st.pnl_estimate >= 0 ? 'text-green' : 'text-red'}`}>
                    {fmtDollar(st.pnl_estimate)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
