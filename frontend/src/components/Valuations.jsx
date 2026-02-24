import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  getValuationsSummary,
  getValuationsPeers,
  updateValuationsPeers,
  removeValuationsPeer,
  compareValuations,
} from '../api/client';

const EM = '\u2014';

function fmt$(v) {
  if (v == null) return EM;
  const abs = Math.abs(v);
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function fmtRatio(v) {
  if (v == null) return EM;
  return v.toFixed(2) + 'x';
}

function fmtPct(v) {
  if (v == null) return EM;
  const sign = v >= 0 ? '+' : '';
  return sign + v.toFixed(1) + '%';
}

function fmtMargin(v) {
  if (v == null) return EM;
  return v.toFixed(1) + '%';
}

// ========== Summary Table Columns ==========

const TTM_COLS = [
  { key: 'symbol', label: 'Ticker', align: 'left', fmt: v => v },
  { key: 'market_cap', label: 'Market Cap', align: 'right', fmt: fmt$ },
  { key: 'ttm_revenue', label: 'TTM Revenue', align: 'right', fmt: fmt$ },
  { key: 'ttm_net_income', label: 'TTM Net Income', align: 'right', fmt: fmt$ },
  { key: 'forward_revenue', label: 'Fwd 12M Rev', align: 'right', fmt: fmt$ },
  { key: 'forward_net_income', label: 'Fwd 12M NI', align: 'right', fmt: fmt$ },
  { key: 'ps_ratio', label: 'P/S', align: 'right', fmt: fmtRatio },
  { key: 'pe_ratio', label: 'P/E', align: 'right', fmt: fmtRatio },
];

const Q_COLS = [
  { key: 'symbol', label: 'Ticker', align: 'left', fmt: v => v },
  { key: 'market_cap', label: 'Market Cap', align: 'right', fmt: fmt$ },
  { key: 'latest_q_revenue', label: 'Latest Q Rev', align: 'right', fmt: fmt$ },
  { key: 'latest_q_net_income', label: 'Latest Q NI', align: 'right', fmt: fmt$ },
  { key: 'forward_q_revenue', label: 'Fwd Q Rev', align: 'right', fmt: fmt$ },
  { key: 'forward_q_net_income', label: 'Fwd Q NI', align: 'right', fmt: fmt$ },
];

// ========== Comparison Metrics ==========

const COMPARE_METRICS = [
  { key: 'market_cap', label: 'Market Cap', fmt: fmt$ },
  { key: 'enterprise_value', label: 'Enterprise Value', fmt: fmt$ },
  { key: 'total_cash', label: 'Cash', fmt: fmt$ },
  { key: 'total_debt', label: 'Total Debt', fmt: fmt$ },
  { key: 'net_cash', label: 'Net Cash / Debt', fmt: fmt$ },
  { key: 'ttm_revenue', label: 'TTM Revenue', fmt: fmt$ },
  { key: 'ttm_net_income', label: 'TTM Net Income', fmt: fmt$ },
  { key: 'gross_margin', label: 'Gross Margin', fmt: fmtMargin },
  { key: 'operating_margin', label: 'Operating Margin', fmt: fmtMargin },
  { key: 'net_margin', label: 'Net Margin', fmt: fmtMargin },
  { key: 'free_cash_flow', label: 'Free Cash Flow', fmt: fmt$ },
  { key: 'ev_sales', label: 'EV / Sales', fmt: fmtRatio },
  { key: 'ev_ebitda', label: 'EV / EBITDA', fmt: fmtRatio },
  { key: 'ps_ratio', label: 'P/S', fmt: fmtRatio },
  { key: 'pe_ratio', label: 'P/E', fmt: fmtRatio },
  { key: 'revenue_growth_yoy', label: 'Rev YoY Growth', fmt: fmtPct },
  { key: 'perf_1m', label: '1M Performance', fmt: fmtPct },
  { key: 'perf_3m', label: '3M Performance', fmt: fmtPct },
  { key: 'perf_1y', label: '1Y Performance', fmt: fmtPct },
];

// ========== Main Component ==========

export default function Valuations() {
  const [summaryData, setSummaryData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [viewMode, setViewMode] = useState('ttm');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [searchFilter, setSearchFilter] = useState('');
  const [sortKey, setSortKey] = useState('market_cap');
  const [sortAsc, setSortAsc] = useState(false);
  const [expandedTicker, setExpandedTicker] = useState(null);
  const [peersData, setPeersData] = useState(null);
  const [peersLoading, setPeersLoading] = useState(false);

  // Comparison state
  const [compareSymbols, setCompareSymbols] = useState(['', '', '']);
  const [compareData, setCompareData] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState('');

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getValuationsSummary(sourceFilter);
      setSummaryData(data.tickers || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [sourceFilter]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  const columns = viewMode === 'ttm' ? TTM_COLS : Q_COLS;

  const filtered = useMemo(() => {
    let rows = summaryData;
    if (searchFilter) {
      const q = searchFilter.toUpperCase();
      rows = rows.filter(r => r.symbol?.toUpperCase().includes(q));
    }
    return [...rows].sort((a, b) => {
      let va = a[sortKey], vb = b[sortKey];
      if (va == null) va = sortAsc ? Infinity : -Infinity;
      if (vb == null) vb = sortAsc ? Infinity : -Infinity;
      if (typeof va === 'string') { va = va.toLowerCase(); vb = (vb || '').toLowerCase(); }
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [summaryData, searchFilter, sortKey, sortAsc]);

  function handleSort(key) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  }

  async function handleExpand(ticker) {
    if (expandedTicker === ticker) {
      setExpandedTicker(null);
      setPeersData(null);
      return;
    }
    setExpandedTicker(ticker);
    setPeersLoading(true);
    setPeersData(null);
    try {
      const data = await getValuationsPeers(ticker);
      setPeersData(data.peers || []);
    } catch {
      setPeersData([]);
    } finally {
      setPeersLoading(false);
    }
  }

  async function handleAddPeer(ticker, newPeer) {
    if (!newPeer || !ticker) return;
    const currentSymbols = (peersData || []).map(p => p.symbol);
    const upper = newPeer.toUpperCase().trim();
    if (currentSymbols.includes(upper)) return;
    try {
      await updateValuationsPeers(ticker, [...currentSymbols, upper]);
      // Refresh peers
      const data = await getValuationsPeers(ticker);
      setPeersData(data.peers || []);
    } catch (err) {
      console.error('Failed to add peer:', err.message);
    }
  }

  async function handleRemovePeer(ticker, peerSymbol) {
    try {
      await removeValuationsPeer(ticker, peerSymbol);
      setPeersData(prev => (prev || []).filter(p => p.symbol !== peerSymbol));
    } catch (err) {
      console.error('Failed to remove peer:', err.message);
    }
  }

  function handleCompareInput(idx, val) {
    setCompareSymbols(prev => {
      const next = [...prev];
      next[idx] = val.toUpperCase();
      return next;
    });
  }

  async function handleCompare() {
    const symbols = compareSymbols.filter(s => s.trim());
    if (symbols.length === 0) return;
    setCompareLoading(true);
    setCompareError('');
    setCompareData(null);
    try {
      const data = await compareValuations(symbols);
      setCompareData(data.companies || []);
    } catch (err) {
      setCompareError(err.message);
    } finally {
      setCompareLoading(false);
    }
  }

  // Quick-fill comparison from summary ticker list
  const availableTickers = useMemo(() =>
    summaryData.map(d => d.symbol).filter(Boolean),
    [summaryData]
  );

  return (
    <div className="valuations-tab">
      {/* Header */}
      <div className="valuations-header">
        <div>
          <h1 className="valuations-title">Valuations</h1>
          <p className="valuations-subtitle">
            Fundamental data across your portfolio and watchlist
          </p>
        </div>
      </div>

      {error && <div className="error-msg">{error}</div>}

      {/* Controls Bar */}
      <div className="val-controls">
        <div className="val-controls-left">
          <div className="val-toggle-group">
            <button
              className={`val-toggle-btn ${viewMode === 'ttm' ? 'active' : ''}`}
              onClick={() => setViewMode('ttm')}
            >
              Trailing 12Ms
            </button>
            <button
              className={`val-toggle-btn ${viewMode === 'quarter' ? 'active' : ''}`}
              onClick={() => setViewMode('quarter')}
            >
              Quarterly
            </button>
          </div>
          <select
            className="val-filter-select"
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
          >
            <option value="all">All</option>
            <option value="portfolio">Portfolio Only</option>
            <option value="watchlist">Watchlist Only</option>
          </select>
        </div>
        <input
          className="val-search"
          type="text"
          placeholder="Filter by ticker..."
          value={searchFilter}
          onChange={e => setSearchFilter(e.target.value)}
        />
      </div>

      {/* Summary Table */}
      {loading ? (
        <div className="loading"><span className="spinner" /> Loading valuations...</div>
      ) : filtered.length === 0 ? (
        <div className="val-empty">
          <p>No tickers found. Add positions or watchlist tickers to see valuations.</p>
        </div>
      ) : (
        <div className="val-table-wrapper">
          <table className="val-table">
            <thead>
              <tr>
                {columns.map(col => (
                  <th
                    key={col.key}
                    className={`${col.align === 'right' ? 'text-right' : ''} sort-header ${sortKey === col.key ? 'sorted' : ''}`}
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                    {sortKey === col.key && (
                      <span className="sort-arrow">{sortAsc ? ' \u25B2' : ' \u25BC'}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => (
                <SummaryRow
                  key={row.symbol}
                  row={row}
                  columns={columns}
                  expanded={expandedTicker === row.symbol}
                  onExpand={() => handleExpand(row.symbol)}
                  peersData={expandedTicker === row.symbol ? peersData : null}
                  peersLoading={expandedTicker === row.symbol && peersLoading}
                  onAddPeer={(peer) => handleAddPeer(row.symbol, peer)}
                  onRemovePeer={(peer) => handleRemovePeer(row.symbol, peer)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Comparison Tool */}
      <div className="val-compare-section">
        <h2 className="val-section-title">Comparison Tool</h2>
        <p className="val-section-subtitle">Compare up to 3 companies side by side</p>

        <div className="val-compare-inputs">
          {[0, 1, 2].map(idx => (
            <div key={idx} className="val-compare-input-wrapper">
              <input
                className="val-compare-input"
                type="text"
                placeholder={`Ticker ${idx + 1}`}
                value={compareSymbols[idx]}
                onChange={e => handleCompareInput(idx, e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleCompare(); }}
                list={`ticker-list-${idx}`}
              />
              <datalist id={`ticker-list-${idx}`}>
                {availableTickers.map(t => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </div>
          ))}
          <button
            className="btn-primary"
            onClick={handleCompare}
            disabled={compareLoading || compareSymbols.every(s => !s.trim())}
          >
            {compareLoading ? 'Loading...' : 'Compare'}
          </button>
        </div>

        {compareError && <div className="error-msg">{compareError}</div>}

        {compareData && compareData.length > 0 && (
          <div className="val-table-wrapper">
            <table className="val-table val-compare-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  {compareData.map(c => (
                    <th key={c.symbol} className="text-right">{c.symbol}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE_METRICS.map(metric => (
                  <tr key={metric.key}>
                    <td className="val-metric-label">{metric.label}</td>
                    {compareData.map(c => (
                      <td key={c.symbol} className="text-right">
                        <span className={getValueColor(metric.key, c[metric.key])}>
                          {metric.fmt(c[metric.key])}
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ========== Sub-components ==========

function SummaryRow({ row, columns, expanded, onExpand, peersData, peersLoading, onAddPeer, onRemovePeer }) {
  const [addInput, setAddInput] = useState('');

  function handleAdd(e) {
    e.preventDefault();
    e.stopPropagation();
    if (addInput.trim()) {
      onAddPeer(addInput.trim());
      setAddInput('');
    }
  }

  return (
    <>
      <tr className={`val-row ${expanded ? 'expanded' : ''}`} onClick={onExpand}>
        {columns.map(col => (
          <td key={col.key} className={col.align === 'right' ? 'text-right' : ''}>
            {col.key === 'symbol' ? (
              <span className="val-ticker">
                <span className="val-expand-icon">{expanded ? '\u25BC' : '\u25B6'}</span>
                {row.symbol}
              </span>
            ) : (
              <span className={getValueColor(col.key, row[col.key])}>
                {col.fmt(row[col.key])}
              </span>
            )}
          </td>
        ))}
      </tr>
      {expanded && (
        <tr className="val-peers-row">
          <td colSpan={columns.length}>
            {peersLoading ? (
              <div className="val-peers-loading"><span className="spinner" /> Loading peers...</div>
            ) : !peersData || peersData.length === 0 ? (
              <div className="val-peers-empty">No peers configured.</div>
            ) : (
              <div className="val-peers-table-wrapper">
                <table className="val-table val-peers-inner">
                  <thead>
                    <tr>
                      {columns.map(col => (
                        <th key={col.key} className={col.align === 'right' ? 'text-right' : ''}>
                          {col.label}
                        </th>
                      ))}
                      <th style={{ width: 32 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {peersData.map(peer => (
                      <tr key={peer.symbol} className="val-peer-row">
                        {columns.map(col => (
                          <td key={col.key} className={col.align === 'right' ? 'text-right' : ''}>
                            {col.key === 'symbol' ? (
                              <span className="val-peer-ticker">{peer.symbol}</span>
                            ) : (
                              <span className={getValueColor(col.key, peer[col.key])}>
                                {col.fmt(peer[col.key])}
                              </span>
                            )}
                          </td>
                        ))}
                        <td className="peer-remove-cell" onClick={e => e.stopPropagation()}>
                          <button
                            className="btn-remove peer-remove-btn"
                            title={`Remove ${peer.symbol}`}
                            onClick={() => onRemovePeer(peer.symbol)}
                          >
                            &times;
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {/* Add peer input */}
            <form className="peer-add-form" onSubmit={handleAdd} onClick={e => e.stopPropagation()}>
              <input
                className="peer-add-input"
                type="text"
                value={addInput}
                onChange={e => setAddInput(e.target.value.toUpperCase())}
                placeholder="Add peer ticker..."
                maxLength={6}
              />
              <button type="submit" className="btn-primary btn-sm peer-add-btn" disabled={!addInput.trim()}>
                Add
              </button>
            </form>
          </td>
        </tr>
      )}
    </>
  );
}

function getValueColor(key, val) {
  if (val == null) return '';
  if (key === 'net_cash') return val >= 0 ? 'text-green' : 'text-red';
  if (key.includes('perf_') || key === 'revenue_growth_yoy') return val >= 0 ? 'text-green' : 'text-red';
  if (key === 'ttm_net_income' || key === 'latest_q_net_income' || key === 'forward_net_income')
    return val >= 0 ? 'text-green' : 'text-red';
  return '';
}
