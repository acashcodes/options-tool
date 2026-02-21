import { useState, useEffect, useCallback } from 'react';
import { getEnrichedPortfolio } from '../api/client';
import ManagePortfolioModal from './ManagePortfolioModal';
import HoldingsTable from './HoldingsTable';
import PortfolioCharts from './PortfolioCharts';
import MarketOverviewBar from './MarketOverviewBar';
import AlertsPanel from './AlertsPanel';
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
    tooltip: 'Gamma measures how your delta accelerates on big moves. Positive gamma (long options) means profits accelerate as the market moves in your favor. Negative gamma (short options) means losses accelerate on large moves. Think of it as convexity.',
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
    tooltip: 'Vega is your sensitivity to changes in implied volatility. Positive vega = you profit when IV rises (long options, good before earnings). Negative vega = you profit when IV falls (short options, good after IV crush).',
  },
  options_pnl: {
    label: 'Options P&L',
    actionable: (v) => {
      if (v == null) return 'No options positions';
      if (v > 0) return 'Options trades are profitable';
      if (v < 0) return 'Options trades are underwater';
      return 'Options trades at breakeven';
    },
    tooltip: 'Total profit/loss from your options positions only, separated from stock P&L. Helps you track whether your options bets are paying off independently.',
  },
};

export default function Dashboard({ onNavigateToAnalysis }) {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [marginAmount, setMarginAmount] = useState(() => {
    const saved = localStorage.getItem('portfolio_margin');
    return saved || '';
  });
  const [editingLeverage, setEditingLeverage] = useState(false);

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

  function handleLeverageSave() {
    if (marginAmount.trim()) {
      localStorage.setItem('portfolio_margin', marginAmount.trim());
    } else {
      localStorage.removeItem('portfolio_margin');
    }
    setEditingLeverage(false);
  }

  const m = portfolio?.metrics;
  const positions = portfolio?.positions || [];
  const isEmpty = positions.length === 0;

  // Compute options P&L from positions
  const optionsPnl = positions
    .filter(p => p.asset_type === 'call' || p.asset_type === 'put')
    .reduce((sum, p) => sum + (p.pnl || 0), 0);
  const hasOptions = positions.some(p => p.asset_type === 'call' || p.asset_type === 'put');

  // Display leverage: if margin $ is set, leverage = gross_exposure / margin
  const parsedMargin = marginAmount.trim() ? parseFloat(marginAmount) : null;
  const leverageVal = parsedMargin && parsedMargin > 0 && m?.gross_exposure
    ? m.gross_exposure / parsedMargin
    : m?.leverage_ratio;
  const displayLeverage = leverageVal != null ? `${leverageVal.toFixed(2)}x` : '\u2014';
  const marginLabel = parsedMargin ? `$${Number(parsedMargin).toLocaleString('en-US', { maximumFractionDigits: 0 })} margin` : null;

  return (
    <div className="dashboard portfolio-dashboard">
      {/* Market Overview Bar */}
      <MarketOverviewBar />

      {/* Alerts Panel */}
      <AlertsPanel onNavigateToAnalysis={onNavigateToAnalysis} />

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

          {/* Watchlist visible even with empty portfolio */}
          <WatchlistTable onNavigateToAnalysis={onNavigateToAnalysis} />
        </>
      )}

      {!loading && !isEmpty && m && (
        <>
          {/* Metrics Bar */}
          <div className="metrics-bar">
            <MetricCard label="Market Value" value={fmtDollar(m.total_market_value)} />
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
            <MetricCard
              label="Gross Exposure"
              value={fmtDollar(m.gross_exposure)}
            />
            <MetricCard
              label="Net Exposure"
              value={fmtDollar(m.net_exposure)}
              color={m.net_exposure >= 0 ? 'cyan' : 'red'}
            />
            <LeverageCard
              value={displayLeverage}
              leverageVal={leverageVal}
              editing={editingLeverage}
              inputVal={marginAmount}
              onEdit={() => setEditingLeverage(true)}
              onChange={setMarginAmount}
              onSave={handleLeverageSave}
              onCancel={() => { setEditingLeverage(false); setMarginAmount(localStorage.getItem('portfolio_margin') || ''); }}
              marginLabel={marginLabel}
            />
          </div>

          {/* Greeks Bar */}
          <div className="greeks-bar">
            <GreekCard
              info={GREEK_INFO.delta}
              value={fmtGreek(m.greeks.delta)}
              rawValue={m.greeks.delta}
              color={m.greeks.delta > 0 ? 'cyan' : m.greeks.delta < 0 ? 'red' : null}
            />
            <GreekCard
              info={GREEK_INFO.gamma}
              value={gammaGauge(m.greeks.gamma)}
              rawValue={m.greeks.gamma}
              color={m.greeks.gamma > 0 ? 'cyan' : m.greeks.gamma < 0 ? 'red' : null}
            />
            <GreekCard
              info={GREEK_INFO.theta}
              value={fmtGreek(m.greeks.theta)}
              rawValue={m.greeks.theta}
              color={m.greeks.theta < 0 ? 'red' : 'cyan'}
            />
            <GreekCard
              info={GREEK_INFO.vega}
              value={fmtGreek(m.greeks.vega)}
              rawValue={m.greeks.vega}
              color={m.greeks.vega > 0 ? 'cyan' : m.greeks.vega < 0 ? 'red' : null}
            />
            <GreekCard
              info={GREEK_INFO.options_pnl}
              value={hasOptions ? fmtPnl(optionsPnl) : '\u2014'}
              rawValue={hasOptions ? optionsPnl : null}
              color={hasOptions ? (optionsPnl >= 0 ? 'cyan' : 'red') : null}
            />
          </div>

          {/* Risk Flags */}
          {m.risk_flags && m.risk_flags.length > 0 && (
            <div className="risk-flags">
              {m.risk_flags.map((f, i) => (
                <div key={i} className="risk-flag">{f}</div>
              ))}
            </div>
          )}

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

function MetricCard({ label, value, sub, color }) {
  return (
    <div className="port-metric-card">
      <span className="port-metric-label">{label}</span>
      <span className={`port-metric-value ${color ? `color-${color}` : ''}`}>{value}</span>
      {sub && <span className={`port-metric-sub ${color ? `color-${color}` : ''}`}>{sub}</span>}
    </div>
  );
}

function LeverageCard({ value, leverageVal, editing, inputVal, onEdit, onChange, onSave, onCancel, marginLabel }) {
  return (
    <div className="port-metric-card leverage-card">
      <span className="port-metric-label">Leverage</span>
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
          className={`port-metric-value leverage-clickable ${leverageVal != null && leverageVal > 1.5 ? 'color-red' : ''}`}
          onClick={onEdit}
          title="Click to set margin amount"
        >
          {value}
        </span>
      )}
      {marginLabel && !editing && <span className="port-metric-sub">{marginLabel}</span>}
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
