import { useState, useEffect } from 'react';
import { getOptionsExpirations, getOptionsChain } from '../api/client';

function fmt(n) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtInt(n) {
  if (n == null) return '—';
  return n.toLocaleString();
}

function fmtIV(n) {
  if (n == null) return '—';
  return `${n.toFixed(1)}%`;
}

function daysUntil(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.round((d - now) / 86400000);
}

function formatExpiry(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const month = d.toLocaleString('en-US', { month: 'short' });
  const day = d.getDate();
  const dte = daysUntil(dateStr);
  return `${month} ${day} (${dte}d)`;
}

function ChainTable({ options, type, volumeThreshold }) {
  if (!options || options.length === 0) {
    return <div className="loading">No {type} data available</div>;
  }

  return (
    <div className="chain-table-wrapper">
      <table className="chain-table">
        <thead>
          <tr>
            <th>Strike</th>
            <th>Last</th>
            <th>Bid</th>
            <th>Ask</th>
            <th>Vol</th>
            <th>OI</th>
            <th>IV</th>
          </tr>
        </thead>
        <tbody>
          {options.map((opt) => (
            <tr key={`${type}-${opt.strike}`} className={opt.in_the_money ? 'itm' : ''}>
              <td className="strike-col">{fmt(opt.strike)}</td>
              <td>{fmt(opt.last_price)}</td>
              <td>{fmt(opt.bid)}</td>
              <td>{fmt(opt.ask)}</td>
              <td className={opt.volume >= volumeThreshold ? 'high-volume' : ''}>
                {opt.volume != null ? fmtInt(opt.volume) : <span className="nil">—</span>}
              </td>
              <td className={opt.open_interest >= volumeThreshold ? 'high-volume' : ''}>
                {opt.open_interest != null ? fmtInt(opt.open_interest) : <span className="nil">—</span>}
              </td>
              <td>{fmtIV(opt.implied_volatility)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OptionsChain({ symbol, currentPrice }) {
  const [expirations, setExpirations] = useState([]);
  const [selectedExpiry, setSelectedExpiry] = useState(null);
  const [chain, setChain] = useState(null);
  const [viewType, setViewType] = useState('both'); // calls, puts, both
  const [strikeRange, setStrikeRange] = useState(20); // percentage
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch expirations when symbol changes
  useEffect(() => {
    let cancelled = false;
    setExpirations([]);
    setSelectedExpiry(null);
    setChain(null);
    setError(null);

    async function load() {
      try {
        const data = await getOptionsExpirations(symbol);
        if (cancelled) return;
        setExpirations(data.expirations || []);
        if (data.expirations?.length > 0) {
          setSelectedExpiry(data.expirations[0]);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [symbol]);

  // Fetch chain when expiry changes
  useEffect(() => {
    if (!selectedExpiry) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function load() {
      try {
        const data = await getOptionsChain(symbol, selectedExpiry);
        if (cancelled) return;
        setChain(data);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [symbol, selectedExpiry]);

  // Filter by strike range
  function filterByStrike(options) {
    if (!options || !currentPrice) return options || [];
    const low = currentPrice * (1 - strikeRange / 100);
    const high = currentPrice * (1 + strikeRange / 100);
    return options.filter((o) => o.strike >= low && o.strike <= high);
  }

  // Compute volume threshold for highlighting (top 20% of volume across all visible options)
  function getVolumeThreshold() {
    if (!chain) return Infinity;
    const allOpts = [...(chain.calls || []), ...(chain.puts || [])];
    const volumes = allOpts
      .map((o) => o.volume)
      .filter((v) => v != null && v > 0)
      .sort((a, b) => b - a);
    if (volumes.length === 0) return Infinity;
    return volumes[Math.floor(volumes.length * 0.2)] || Infinity;
  }

  const filteredCalls = filterByStrike(chain?.calls);
  const filteredPuts = filterByStrike(chain?.puts);
  const volumeThreshold = getVolumeThreshold();

  // Show max 8 expiry tabs, rest in overflow
  const visibleExpiries = expirations.slice(0, 8);
  const overflowExpiries = expirations.slice(8);
  const isOverflowSelected = overflowExpiries.includes(selectedExpiry);

  return (
    <div className="options-chain">
      <h2>Options Chain</h2>

      {expirations.length > 0 && (
        <div className="chain-controls">
          <div className="expiry-tabs">
            {visibleExpiries.map((exp) => (
              <button
                key={exp}
                className={selectedExpiry === exp ? 'active' : ''}
                onClick={() => setSelectedExpiry(exp)}
              >
                {formatExpiry(exp)}
              </button>
            ))}
            {overflowExpiries.length > 0 && (
              <select
                value={isOverflowSelected ? selectedExpiry : ''}
                onChange={(e) => setSelectedExpiry(e.target.value)}
                style={{
                  background: isOverflowSelected ? 'var(--accent-cyan)' : 'var(--bg-tertiary)',
                  color: isOverflowSelected ? 'var(--bg-primary)' : 'var(--text-secondary)',
                }}
              >
                <option value="" disabled>More...</option>
                {overflowExpiries.map((exp) => (
                  <option key={exp} value={exp}>{formatExpiry(exp)}</option>
                ))}
              </select>
            )}
          </div>

          <div className="type-toggle">
            {['calls', 'both', 'puts'].map((t) => (
              <button
                key={t}
                className={viewType === t ? 'active' : ''}
                onClick={() => setViewType(t)}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="strike-range">
            <label>Range</label>
            <input
              type="range"
              min={5}
              max={50}
              step={5}
              value={strikeRange}
              onChange={(e) => setStrikeRange(Number(e.target.value))}
            />
            <span className="range-value">{strikeRange}%</span>
          </div>
        </div>
      )}

      {error && <div className="error-msg">{error}</div>}

      {loading && (
        <div className="loading">
          <span className="spinner" />
          Loading options chain...
        </div>
      )}

      {!loading && chain && (
        viewType === 'both' ? (
          <div className="chain-side-by-side">
            <div className="chain-section calls">
              <h3>Calls</h3>
              <ChainTable options={filteredCalls} type="call" volumeThreshold={volumeThreshold} />
            </div>
            <div className="chain-section puts">
              <h3>Puts</h3>
              <ChainTable options={filteredPuts} type="put" volumeThreshold={volumeThreshold} />
            </div>
          </div>
        ) : viewType === 'calls' ? (
          <ChainTable options={filteredCalls} type="call" volumeThreshold={volumeThreshold} />
        ) : (
          <ChainTable options={filteredPuts} type="put" volumeThreshold={volumeThreshold} />
        )
      )}
    </div>
  );
}
