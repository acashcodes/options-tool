import { useState, useEffect } from 'react';
import {
  getEnrichedWatchlist,
  addWatchlistTicker,
  removeWatchlistTicker,
} from '../api/client';

const COLUMNS = [
  { key: 'ticker', label: 'Ticker', align: 'left' },
  { key: 'price', label: 'Price', align: 'right' },
  { key: 'change', label: 'Change', align: 'right' },
  { key: 'change_percent', label: 'Change %', align: 'right' },
  { key: 'iv_rank', label: 'IV Rank', align: 'right' },
  { key: 'iv_percentile', label: 'IV Pctile', align: 'right' },
  { key: 'high_52w', label: '52W High', align: 'right' },
  { key: 'low_52w', label: '52W Low', align: 'right' },
  { key: 'earnings_date', label: 'Earnings', align: 'right' },
];

function fmt(v) {
  if (v == null) return '\u2014';
  return Number(v).toFixed(2);
}

function fmtPct(v) {
  if (v == null) return '\u2014';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${Number(v).toFixed(2)}%`;
}

function fmtRank(v) {
  if (v == null) return '\u2014';
  return `${Number(v).toFixed(0)}%`;
}

export default function WatchlistTable({ onNavigateToAnalysis }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState('');
  const [adding, setAdding] = useState(false);
  const [sortKey, setSortKey] = useState('ticker');
  const [sortAsc, setSortAsc] = useState(true);

  function fetchWatchlist() {
    setLoading(true);
    getEnrichedWatchlist()
      .then((data) => setItems(data.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => { fetchWatchlist(); }, []);

  async function handleAdd(e) {
    e.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    setAdding(true);
    try {
      await addWatchlistTicker(ticker);
      setInput('');
      fetchWatchlist();
    } catch (err) {
      console.error('Add failed:', err.message);
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(e, ticker) {
    e.stopPropagation();
    try {
      await removeWatchlistTicker(ticker);
      setItems((prev) => prev.filter((it) => it.ticker !== ticker));
    } catch (err) {
      console.error('Remove failed:', err.message);
    }
  }

  function handleSort(key) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(key === 'ticker');
    }
  }

  const sorted = [...items].sort((a, b) => {
    let va = a[sortKey], vb = b[sortKey];
    if (va == null) va = sortAsc ? Infinity : -Infinity;
    if (vb == null) vb = sortAsc ? Infinity : -Infinity;
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });

  function renderCell(item, key) {
    const v = item[key];
    switch (key) {
      case 'ticker':
        return <span className="ticker-cell">{v}</span>;
      case 'price':
        return fmt(v);
      case 'change': {
        const cls = v >= 0 ? 'color-cyan' : 'color-red';
        return <span className={cls}>{v != null ? `${v >= 0 ? '+' : ''}${fmt(v)}` : '\u2014'}</span>;
      }
      case 'change_percent': {
        const cls = v >= 0 ? 'color-cyan' : 'color-red';
        return <span className={cls}>{fmtPct(v)}</span>;
      }
      case 'iv_rank':
      case 'iv_percentile':
        return fmtRank(v);
      case 'high_52w':
      case 'low_52w':
        return fmt(v);
      case 'earnings_date':
        return v || '\u2014';
      default:
        return v ?? '\u2014';
    }
  }

  return (
    <div className="watchlist-section">
      <div className="watchlist-header">
        <h3>Watchlist</h3>
        <span className="holdings-count">{items.length} tickers</span>
      </div>

      <form className="watchlist-add-bar" onSubmit={handleAdd}>
        <input
          type="text"
          placeholder="Add ticker..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={adding}
        />
        <button type="submit" disabled={adding || !input.trim()}>
          {adding ? 'Adding...' : 'Add'}
        </button>
      </form>

      {loading && (
        <div className="loading"><span className="spinner" /> Loading watchlist...</div>
      )}

      {!loading && items.length === 0 && (
        <div className="watchlist-empty">
          Add tickers above to start tracking stocks you're watching.
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="holdings-table-wrapper">
          <table className="holdings-table">
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={`sort-header ${col.align === 'right' ? 'text-right' : ''} ${sortKey === col.key ? 'sorted' : ''}`}
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                    {sortKey === col.key && (
                      <span className="sort-arrow">{sortAsc ? ' \u25B2' : ' \u25BC'}</span>
                    )}
                  </th>
                ))}
                <th className="text-right"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item) => (
                <tr
                  key={item.ticker}
                  className="holdings-row"
                  onClick={() => onNavigateToAnalysis(item.ticker)}
                >
                  {COLUMNS.map((col) => (
                    <td key={col.key} className={col.align === 'right' ? 'text-right' : ''}>
                      {renderCell(item, col.key)}
                    </td>
                  ))}
                  <td className="actions-cell">
                    <button
                      className="btn-remove"
                      title="Remove from watchlist"
                      onClick={(e) => handleRemove(e, item.ticker)}
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
    </div>
  );
}
