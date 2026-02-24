import { useState, useEffect, useCallback } from 'react';
import { getEnrichedPortfolio } from '../api/client';
import ManagePortfolioModal from './ManagePortfolioModal';
import HoldingsTable from './HoldingsTable';
import PortfolioCharts from './PortfolioCharts';
import WatchlistTable from './WatchlistTable';

const GREEK_INFO = {
  delta: {
    label: 'Delta ($)',
    actionable: (v) => {
      if (v == null) return 'No exposure data';
      const move = Math.abs(v * 0.01);
      const fmtMove = move.toLocaleString('en-US', { maximumFractionDigits: 0 });
      if (v > 0) return `Portfolio +$${fmtMove} per 1% up`;
      if (v < 0) return `Portfolio -$${fmtMove} per 1% up`;
      return 'Market-neutral';
    },
    tooltip: 'Dollar Delta is your total directional exposure. Multiply by 0.01 to get how much your portfolio gains or loses for every 1% move in your holdings. Positive = long/bullish bias, Negative = short/bearish bias.',
  },
  gamma: {
    label: 'Gamma',
    actionable: (v) => {
      if (v == null) return 'No gamma exposure';
      const abs = Math.abs(v);
      const dir = v > 0 ? 'Long' : 'Short';
      const fmtVal = abs >= 1000 ? `${(abs / 1000).toFixed(1)}K` : abs.toFixed(0);
      if (v > 0) return `${fmtVal} \u2014 ${dir} convexity, big moves help`;
      if (v < 0) return `${fmtVal} \u2014 ${dir} convexity, big moves hurt`;
      return 'Flat gamma';
    },
    tooltip: 'Gamma measures how your delta accelerates on big moves. Positive gamma (long options) means profits accelerate as the market moves in your favor. Negative gamma (short options) means losses accelerate on large moves.',
  },
  theta: {
    label: 'Theta ($/day)',
    actionable: (v) => {
      if (v == null) return 'No time decay';
      if (v < 0) return `Paying $${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}/day in time decay`;
      if (v > 0) return `Earning $${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}/day from time decay`;
      return 'No daily bleed';
    },
    tooltip: 'Theta is your daily time decay cost. Negative theta means your options positions lose this much value each day just from the passage of time. Positive theta (from selling options) means you collect this daily.',
  },
  vega: {
    label: 'Vega ($)',
    actionable: (v) => {
      if (v == null) return 'No vol exposure';
      if (v > 0) return `+$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })} per 1% IV rise`;
      if (v < 0) return `-$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })} per 1% IV rise`;
      return 'Vol-neutral';
    },
    tooltip: 'Vega is your sensitivity to changes in implied volatility. Positive vega = you profit when IV rises (long options). Negative vega = you profit when IV falls (short options).',
  },
  options_pnl: {
    label: 'Options P&L',
    actionable: (v) => {
      if (v == null) return 'No options positions';
      if (v > 0) return 'Options trades are profitable';
      if (v < 0) return 'Options trades are underwater';
      return 'Options trades at breakeven';
    },
    tooltip: 'Total profit/loss from your options positions only, separated from stock P&L.',
  },
};

export default function PortfolioTab({ onNavigateToAnalysis }) {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [marginAmount, setMarginAmount] = useState(() => {
    const saved = localStorage.getItem('portfolio_margin');
    return saved || '';
  });
  const [editingMargin, setEditingMargin] = useState(false);

  const fetchPortfolio = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getEnrichedPortfolio();
      setPortfolio(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPortfolio(); }, [fetchPortfolio]);

  function handleSaved() {
    setShowModal(false);
    fetchPortfolio();
  }

  function handleMarginSave() {
    if (marginAmount.trim()) {
      localStorage.setItem('portfolio_margin', marginAmount.trim());
    } else {
      localStorage.removeItem('portfolio_margin');
    }
    setEditingMargin(false);
  }

  const m = portfolio?.metrics;
  const positions = portfolio?.positions || [];
  const isEmpty = positions.length === 0;

  // Compute options P&L from positions
  const optionsPnl = positions
    .filter(p => p.asset_type === 'call' || p.asset_type === 'put')
    .reduce((sum, p) => sum + (p.pnl || 0), 0);
  const hasOptions = positions.some(p => p.asset_type === 'call' || p.asset_type === 'put');

  // Leverage computed from margin input
  const parsedMargin = marginAmount.trim() ? parseFloat(marginAmount) : null;
  const leverageVal = parsedMargin && parsedMargin > 0 && m?.gross_exposure
    ? m.gross_exposure / parsedMargin
    : m?.leverage_ratio;

  // Portfolio value = gross total of positions - margin used
  const portfolioValue = parsedMargin && parsedMargin > 0 && m?.total_market_value != null
    ? m.total_market_value - parsedMargin
    : m?.total_market_value;

  // Convenience aliases for metrics row calculations
  const total_mv = m?.total_market_value || 0;
  const greeks = m?.greeks || {};

  return (
    <div className="portfolio-tab">
      {/* Header */}
      <div className="portfolio-header">
        <div>
          <h1 className="portfolio-title">Portfolio</h1>
          <p className="portfolio-subtitle">
            {isEmpty ? 'Add positions to get started' : `${m?.position_count || 0} positions tracked`}
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          Manage Portfolio
        </button>
      </div>

      {error && <div className="error-msg">{error}</div>}

      {loading && (
        <div className="loading"><span className="spinner" /> Loading portfolio...</div>
      )}

      {!loading && isEmpty && (
        <>
          <div className="portfolio-empty">
            <div className="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                <path d="M12 8v4m0 4h.01" />
              </svg>
            </div>
            <h2>No Positions Yet</h2>
            <p>Click "Manage Portfolio" to add stocks and options to track.</p>
            <button className="btn-primary" onClick={() => setShowModal(true)}>
              Add Your First Position
            </button>
          </div>
          <WatchlistTable onNavigateToAnalysis={onNavigateToAnalysis} />
        </>
      )}

      {!loading && !isEmpty && m && (
        <>
          {/* Row 1: Hero Portfolio Value */}
          <div className="port-hero">
            <span className="port-hero-label">Portfolio Value</span>
            <span className="port-hero-value">{fmtDollar(portfolioValue)}</span>
            {parsedMargin && parsedMargin > 0 && (
              <span className="port-hero-sub">
                {fmtDollar(m.total_market_value)} gross &minus; {fmtDollar(parsedMargin)} margin
              </span>
            )}
          </div>

          {/* Row 1: Capital & Core Risk */}
          <div className="metrics-row-label">Capital &amp; Core Risk</div>
          <div className="metrics-bar">
            <MarginCard
              parsedMargin={parsedMargin}
              editing={editingMargin}
              inputVal={marginAmount}
              onEdit={() => setEditingMargin(true)}
              onChange={setMarginAmount}
              onSave={handleMarginSave}
              onCancel={() => { setEditingMargin(false); setMarginAmount(localStorage.getItem('portfolio_margin') || ''); }}
            />
            <MetricCard
              label="Margin Used (% Equity)"
              value={parsedMargin && total_mv ? `${((parsedMargin / total_mv) * 100).toFixed(1)}%` : '\u2014'}
              subtitle="Margin as % of portfolio value"
            />
            <MetricCard
              label="Eff. Leverage"
              value={leverageVal != null ? `${leverageVal.toFixed(2)}x` : '\u2014'}
              color={leverageVal != null && leverageVal > 1.5 ? 'red' : null}
              subtitle="Gross exposure / net exposure"
            />
            <MetricCard
              label="Beta-Adj Delta"
              value={greeks.beta_weighted_delta != null
                ? `$${Number(greeks.beta_weighted_delta).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
                : '\u2014'}
              color={greeks.beta_weighted_delta > 0 ? 'cyan' : greeks.beta_weighted_delta < 0 ? 'red' : null}
              subtitle="SPY-equivalent share exposure"
            />
            <MetricCard
              label="Weekly Theta (%)"
              value={total_mv > 0
                ? `${(greeks.theta * 7 / Math.abs(total_mv) * 100).toFixed(2)}%`
                : '\u2014'}
              color={greeks.theta < 0 ? 'red' : 'cyan'}
              subtitle="7-day time decay as % of portfolio"
            />
            <MetricCard
              label="Vega (% P&L)"
              value={total_mv > 0
                ? `${(greeks.vega / Math.abs(total_mv) * 100).toFixed(2)}%`
                : '\u2014'}
              color={greeks.vega > 0 ? 'cyan' : greeks.vega < 0 ? 'red' : null}
              subtitle="P&L impact per 1% IV change"
            />
            <MetricCard
              label="Top Position"
              value={m.concentration && m.concentration[0]
                ? `${m.concentration[0].ticker || m.concentration[0].symbol || '?'} ${(m.concentration[0].weight || 0).toFixed(0)}%`
                : '\u2014'}
              subtitle="Largest single holding"
            />
            <MetricCard
              label="Top Sector"
              value={(() => {
                if (!m.sector_breakdown) return '\u2014';
                const entries = Object.entries(m.sector_breakdown);
                if (entries.length === 0) return '\u2014';
                const [topSector] = entries.reduce((a, b) => b[1] > a[1] ? b : a);
                return topSector;
              })()}
              subtitle="Most concentrated sector"
            />
          </div>

          {/* Row 2: Time & Expiry Risk */}
          <div className="metrics-row-label">Time &amp; Expiry Risk</div>
          <div className="metrics-bar">
            <MetricCard
              label="Wtd Avg DTE"
              value={m.weighted_avg_dte != null ? `${Math.round(m.weighted_avg_dte)} days` : '\u2014'}
              subtitle="Average days to expiration"
            />
            <MetricCard
              label="Expiring <30d"
              value={m.pct_expiring_30d != null ? `${m.pct_expiring_30d.toFixed(0)}%` : '\u2014'}
              subtitle="% portfolio expiring within 30 days"
            />
            <MetricCard
              label="Expiring <14d"
              value={m.pct_expiring_14d != null ? `${m.pct_expiring_14d.toFixed(0)}%` : '\u2014'}
              color={m.pct_expiring_14d != null && m.pct_expiring_14d > 20 ? 'red' : null}
              subtitle="% portfolio expiring within 14 days"
            />
            <MetricCard
              label="5-Day Decay"
              value={m.five_day_theta_dollars != null ? fmtDollar(m.five_day_theta_dollars) : '\u2014'}
              sub={m.five_day_theta_pct != null ? `${m.five_day_theta_pct.toFixed(2)}%` : null}
              subtitle="Expected time decay over 5 days"
            />
            <MetricCard
              label="Gamma / 1% Move"
              value={m.gamma_per_1pct != null ? fmtDollar(m.gamma_per_1pct) : '\u2014'}
              subtitle="Delta change per 1% underlying move"
            />
          </div>

          {/* Row 3: Scenario & Stress */}
          <div className="metrics-row-label">Scenario &amp; Stress</div>
          <div className="metrics-bar">
            <MetricCard
              label="P&L if -2%"
              value={(() => {
                if (m.stress_tests?.pnl_down_2pct != null) return fmtPnl(m.stress_tests.pnl_down_2pct);
                const d = greeks.delta || 0, g = greeks.gamma || 0;
                const est = d * -0.02 + 0.5 * g * 0.02 * 0.02;
                return fmtPnl(est);
              })()}
              color={(() => {
                const v = m.stress_tests?.pnl_down_2pct ?? ((greeks.delta || 0) * -0.02 + 0.5 * (greeks.gamma || 0) * 0.02 * 0.02);
                return v >= 0 ? 'cyan' : 'red';
              })()}
              subtitle="Estimated loss if market drops 2%"
            />
            <MetricCard
              label="P&L if +2%"
              value={(() => {
                if (m.stress_tests?.pnl_up_2pct != null) return fmtPnl(m.stress_tests.pnl_up_2pct);
                const d = greeks.delta || 0, g = greeks.gamma || 0;
                const est = d * 0.02 + 0.5 * g * 0.02 * 0.02;
                return fmtPnl(est);
              })()}
              color={(() => {
                const v = m.stress_tests?.pnl_up_2pct ?? ((greeks.delta || 0) * 0.02 + 0.5 * (greeks.gamma || 0) * 0.02 * 0.02);
                return v >= 0 ? 'cyan' : 'red';
              })()}
              subtitle="Estimated gain if market rises 2%"
            />
            <MetricCard
              label="P&L if IV -5%"
              value={fmtPnl(m.iv_stress_minus5 != null ? m.iv_stress_minus5 : (greeks.vega || 0) * -5)}
              color={(m.iv_stress_minus5 != null ? m.iv_stress_minus5 : (greeks.vega || 0) * -5) >= 0 ? 'cyan' : 'red'}
              subtitle="Impact of 5% IV contraction"
            />
            <MetricCard
              label="P&L if IV +5%"
              value={fmtPnl(m.iv_stress_plus5 != null ? m.iv_stress_plus5 : (greeks.vega || 0) * 5)}
              color={(m.iv_stress_plus5 != null ? m.iv_stress_plus5 : (greeks.vega || 0) * 5) >= 0 ? 'cyan' : 'red'}
              subtitle="Impact of 5% IV expansion"
            />
            <MetricCard
              label="7-Day Decay"
              value={fmtPnl(m.seven_day_theta != null ? m.seven_day_theta : (greeks.theta || 0) * 7)}
              color={(m.seven_day_theta != null ? m.seven_day_theta : (greeks.theta || 0) * 7) >= 0 ? 'cyan' : 'red'}
              subtitle="P&L if nothing changes for 7 days"
            />
            <MetricCard
              label="Day P&L"
              value={fmtPnl(m.day_pnl)}
              sub={m.day_pnl_percent != null ? `${m.day_pnl_percent >= 0 ? '+' : ''}${m.day_pnl_percent.toFixed(2)}%` : null}
              color={m.day_pnl >= 0 ? 'cyan' : 'red'}
            />
            <MetricCard
              label="Total P&L"
              value={fmtPnl(m.total_pnl)}
              sub={m.total_pnl_percent != null ? `${m.total_pnl_percent >= 0 ? '+' : ''}${m.total_pnl_percent.toFixed(2)}%` : null}
              color={m.total_pnl >= 0 ? 'cyan' : 'red'}
            />
          </div>

          {/* Holdings Table */}
          <HoldingsTable
            positions={positions}
            onNavigateToAnalysis={onNavigateToAnalysis}
            onRefresh={fetchPortfolio}
          />

          {/* Watchlist */}
          <WatchlistTable onNavigateToAnalysis={onNavigateToAnalysis} />

          {/* Charts */}
          <PortfolioCharts
            concentration={m.concentration}
            sectorBreakdown={m.sector_breakdown}
          />
        </>
      )}

      {/* Modal */}
      {showModal && (
        <ManagePortfolioModal onClose={() => setShowModal(false)} onSaved={handleSaved} />
      )}
    </div>
  );
}

function MetricCard({ label, value, sub, color, subtitle }) {
  return (
    <div className="port-metric-card">
      <span className="port-metric-label">{label}</span>
      <span className={`port-metric-value ${color ? `color-${color}` : ''}`}>{value}</span>
      {sub && <span className={`port-metric-sub ${color ? `color-${color}` : ''}`}>{sub}</span>}
      {subtitle && <span className="port-metric-subtitle">{subtitle}</span>}
    </div>
  );
}

function MarginCard({ parsedMargin, editing, inputVal, onEdit, onChange, onSave, onCancel }) {
  return (
    <div className="port-metric-card margin-card">
      <span className="port-metric-label">Margin Used</span>
      {editing ? (
        <div className="leverage-edit-row">
          <span className="leverage-dollar-sign">$</span>
          <input
            className="leverage-input"
            type="number"
            step="1000"
            min="0"
            placeholder="Margin $"
            value={inputVal}
            onChange={e => onChange(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') onSave(); if (e.key === 'Escape') onCancel(); }}
            autoFocus
          />
          <button className="btn-save-inline" onClick={onSave}>{'\u2713'}</button>
          <button className="btn-cancel-inline" onClick={onCancel}>{'\u2715'}</button>
        </div>
      ) : (
        <span
          className="port-metric-value leverage-clickable"
          onClick={onEdit}
          title="Click to set margin amount"
        >
          {parsedMargin ? `$${Number(parsedMargin).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : 'Set margin'}
        </span>
      )}
    </div>
  );
}

function GreekCard({ info, value, rawValue, color }) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div
      className="greek-card greek-card-hoverable"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span className="greek-label">{info.label}</span>
      <span className={`greek-value ${color ? `color-${color}` : ''}`}>{value}</span>
      <span className="greek-actionable">{info.actionable(rawValue)}</span>
      {showTooltip && (
        <div className="greek-tooltip">
          {info.tooltip}
        </div>
      )}
    </div>
  );
}

function fmtDollar(v) {
  if (v == null) return '\u2014';
  return `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtPnl(v) {
  if (v == null) return '\u2014';
  const sign = v >= 0 ? '+' : '';
  return `${sign}$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtGreek(v) {
  if (v == null) return '\u2014';
  return `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function gammaGauge(v) {
  if (v == null || v === 0) return '\u2014';
  const abs = Math.abs(v);
  if (abs < 100) return 'Low';
  if (abs < 1000) return 'Medium';
  return 'High';
}
