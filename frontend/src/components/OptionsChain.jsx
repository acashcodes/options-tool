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

function fmtGreek(n) {
  if (n == null) return '—';
  return n.toFixed(4);
}

function fmtGreek2(n) {
  if (n == null) return '—';
  return n.toFixed(2);
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

function isMonthlyExpiry(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const dayOfWeek = d.getDay(); // 0=Sun...5=Fri
  const dayOfMonth = d.getDate();
  // Third Friday: Friday between 15th-21st
  return dayOfWeek === 5 && dayOfMonth >= 15 && dayOfMonth <= 21;
}

function ChainTable({ options, type, volumeThreshold, onAddLeg, selectedExpiry }) {
  if (!options || options.length === 0) {
    return <div className="loading">No {type} data available</div>;
  }

  function handleRowClick(opt) {
    if (!onAddLeg) return;
    const mid = (opt.bid != null && opt.ask != null) ? +((opt.bid + opt.ask) / 2).toFixed(2) : opt.last_price;
    onAddLeg({
      type: type === 'call' ? 'Call' : 'Put',
      strike: opt.strike,
      expiration: selectedExpiry,
      action: 'buy',
      quantity: 1,
      premium: mid,
      bid: opt.bid,
      ask: opt.ask,
      iv: opt.implied_volatility,
    });
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
            <th className="greek-col" title="How much the option price changes per $1 move in the stock">Delta</th>
            <th className="greek-col" title="Rate of change of delta — how fast delta shifts">Gamma</th>
            <th className="greek-col" title="Daily time decay — how much value the option loses per day">Theta</th>
            <th className="greek-col" title="Sensitivity to volatility — price change per 1% IV move">Vega</th>
          </tr>
        </thead>
        <tbody>
          {options.map((opt) => (
            <tr
              key={`${type}-${opt.strike}`}
              className={`${opt.in_the_money ? 'itm' : ''} chain-row-clickable`}
              onClick={() => handleRowClick(opt)}
              title={`Click to add ${type} @ ${opt.strike} to strategy`}
            >
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
              <td className="greek-cell">{opt.delta != null ? fmtGreek2(opt.delta) : '—'}</td>
              <td className="greek-cell">{fmtGreek(opt.gamma)}</td>
              <td className="greek-cell">{opt.theta != null ? fmtGreek2(opt.theta) : '—'}</td>
              <td className="greek-cell">{opt.vega != null ? fmtGreek2(opt.vega) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OptionsChain({ symbol, currentPrice, onAddLeg }) {
  const [expirations, setExpirations] = useState([]);
  const [selectedExpiry, setSelectedExpiry] = useState(null);
  const [chain, setChain] = useState(null);
  const [viewType, setViewType] = useState('both');
  const [strikeRange, setStrikeRange] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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

  function filterByStrike(options) {
    if (!options || !currentPrice) return options || [];
    const low = currentPrice * (1 - strikeRange / 100);
    const high = currentPrice * (1 + strikeRange / 100);
    return options.filter((o) => o.strike >= low && o.strike <= high);
  }

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

  // Chain summary metrics
  let atmIV = null, expectedMove = null, pcRatio = null, totalVol = 0;
  if (chain && currentPrice) {
    const allCalls = chain.calls || [];
    const allPuts = chain.puts || [];

    const atmCall = allCalls.length ? allCalls.reduce((best, c) => Math.abs(c.strike - currentPrice) < Math.abs(best.strike - currentPrice) ? c : best) : null;
    const atmPut = allPuts.length ? allPuts.reduce((best, p) => Math.abs(p.strike - currentPrice) < Math.abs(best.strike - currentPrice) ? p : best) : null;

    if (atmCall?.implied_volatility && atmPut?.implied_volatility) {
      atmIV = (atmCall.implied_volatility + atmPut.implied_volatility) / 2;
    }

    if (atmCall?.last_price != null && atmPut?.last_price != null && currentPrice) {
      const straddle = (atmCall.bid != null && atmCall.ask != null ? (atmCall.bid + atmCall.ask) / 2 : atmCall.last_price) +
                       (atmPut.bid != null && atmPut.ask != null ? (atmPut.bid + atmPut.ask) / 2 : atmPut.last_price);
      expectedMove = (straddle / currentPrice) * 100;
    }

    const callVol = allCalls.reduce((s, c) => s + (c.volume || 0), 0);
    const putVol = allPuts.reduce((s, p) => s + (p.volume || 0), 0);
    totalVol = callVol + putVol;
    pcRatio = callVol > 0 ? putVol / callVol : null;
  }

  const visibleExpiries = expirations.slice(0, 8);
  const overflowExpiries = expirations.slice(8);
  const isOverflowSelected = overflowExpiries.includes(selectedExpiry);

  return (
    <div className="options-chain">
      <h2>Options Chain</h2>

      {expirations.length > 0 && (
        <div className="chain-controls">
          <div className="expiry-tabs">
            {visibleExpiries.map((exp) => {
              const dte = daysUntil(exp);
              const isNearTerm = dte <= 7;
              const isMonthly = isMonthlyExpiry(exp);
              return (
                <button
                  key={exp}
                  className={`${selectedExpiry === exp ? 'active' : ''} ${isNearTerm ? 'expiry-near' : ''}`}
                  onClick={() => setSelectedExpiry(exp)}
                >
                  {formatExpiry(exp)}
                  {isMonthly ? <span className="expiry-badge monthly">M</span> : <span className="expiry-badge weekly">W</span>}
                </button>
              );
            })}
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

      {!loading && chain && (
        <div className="chain-summary-bar">
          {atmIV != null && <div className="chain-summary-item"><span className="chain-summary-label">ATM IV</span><span className="chain-summary-value">{atmIV.toFixed(1)}%</span></div>}
          {expectedMove != null && <div className="chain-summary-item"><span className="chain-summary-label">Expected Move</span><span className="chain-summary-value">&plusmn;{expectedMove.toFixed(1)}%</span></div>}
          {pcRatio != null && <div className="chain-summary-item"><span className="chain-summary-label">P/C Ratio</span><span className={`chain-summary-value ${pcRatio > 1 ? 'color-red' : 'color-cyan'}`}>{pcRatio.toFixed(2)}</span></div>}
          <div className="chain-summary-item"><span className="chain-summary-label">Total Volume</span><span className="chain-summary-value">{totalVol.toLocaleString()}</span></div>
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
              <ChainTable options={filteredCalls} type="call" volumeThreshold={volumeThreshold} onAddLeg={onAddLeg} selectedExpiry={selectedExpiry} />
            </div>
            <div className="chain-section puts">
              <h3>Puts</h3>
              <ChainTable options={filteredPuts} type="put" volumeThreshold={volumeThreshold} onAddLeg={onAddLeg} selectedExpiry={selectedExpiry} />
            </div>
          </div>
        ) : viewType === 'calls' ? (
          <ChainTable options={filteredCalls} type="call" volumeThreshold={volumeThreshold} onAddLeg={onAddLeg} selectedExpiry={selectedExpiry} />
        ) : (
          <ChainTable options={filteredPuts} type="put" volumeThreshold={volumeThreshold} onAddLeg={onAddLeg} selectedExpiry={selectedExpiry} />
        )
      )}
    </div>
  );
}
