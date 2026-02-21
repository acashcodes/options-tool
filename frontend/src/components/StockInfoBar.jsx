function fmt(n) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtCompact(n) {
  if (n == null) return '—';
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toLocaleString()}`;
}

function pctInRange(val, low, high) {
  if (val == null || low == null || high == null || high === low) return 0;
  return Math.max(0, Math.min(100, ((val - low) / (high - low)) * 100));
}

function ivRatioInfo(ratio) {
  if (ratio == null) return null;
  if (ratio >= 1.3) return { text: 'IV Rich', cls: 'ratio-high' };
  if (ratio >= 0.8) return { text: 'Normal', cls: 'ratio-normal' };
  return { text: 'IV Cheap', cls: 'ratio-low' };
}

export default function StockInfoBar({ quote }) {
  const changeClass = quote.change >= 0 ? 'positive' : 'negative';
  const changeSign = quote.change >= 0 ? '+' : '';
  const pricePos = pctInRange(quote.price, quote.low_52w, quote.high_52w);

  const maxIV = Math.max(quote.current_iv || 0, quote.hv_20d || 0, 1);
  const ivPct = quote.current_iv != null ? (quote.current_iv / maxIV) * 100 : 0;
  const hvPct = quote.hv_20d != null ? (quote.hv_20d / maxIV) * 100 : 0;
  const ratioInfo = ivRatioInfo(quote.iv_hv_ratio);

  return (
    <div className="stock-info-panel">
      {/* Top header bar */}
      <div className="stock-info-header">
        <div className="ticker-name">
          <span className="symbol">{quote.symbol}</span>
          <span className="name">{quote.name}</span>
        </div>

        <div className="price-block">
          <span className="price">${fmt(quote.price)}</span>
          {quote.change != null && (
            <span className={`change ${changeClass}`}>
              {changeSign}{fmt(quote.change)} ({changeSign}{quote.change_percent}%)
            </span>
          )}
        </div>

        <div className="header-stats">
          <div className="header-stat">
            <span className="label">Mkt Cap</span>
            <span className="value">{fmtCompact(quote.market_cap)}</span>
          </div>
          <div className="header-stat">
            <span className="label">Volume</span>
            <span className="value">{quote.volume != null ? quote.volume.toLocaleString() : '—'}</span>
          </div>
          {quote.earnings_date && (
            <div className="header-stat">
              <span className="label">Earnings</span>
              <span className="value">{quote.earnings_date}</span>
            </div>
          )}
        </div>
      </div>

      {/* Metric cards with visuals */}
      <div className="stock-info-metrics">
        {/* 52-Week Price Range */}
        <div className="metric-card">
          <div className="metric-label">52-Week Range</div>
          <div className="metric-value">${fmt(quote.price)}</div>
          <div className="range-bar">
            <div
              className="range-bar-fill fill-cyan"
              style={{ width: `${pricePos}%` }}
            />
            <div
              className="range-bar-marker"
              style={{ left: `${pricePos}%` }}
            />
          </div>
          <div className="range-bar-labels">
            <span>${fmt(quote.low_52w)}</span>
            <span>${fmt(quote.high_52w)}</span>
          </div>
        </div>

        {/* IV vs HV Comparison — horizontal bars */}
        <div className="metric-card iv-metric-card">
          <div className="metric-label">Implied vs Historical Vol</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
            <div className="metric-value" style={{ marginBottom: 0 }}>
              {quote.current_iv != null ? `${quote.current_iv.toFixed(1)}%` : '—'}
            </div>
            {ratioInfo && (
              <span className={`iv-ratio-badge ${ratioInfo.cls}`}>
                {ratioInfo.text}
              </span>
            )}
          </div>
          <div className="iv-h-bars">
            <div className="iv-h-row">
              <span className="iv-h-label">IV</span>
              <div className="iv-h-track">
                <div className="iv-h-fill fill-cyan" style={{ width: `${ivPct}%` }} />
                {quote.hv_20d != null && (
                  <div className="iv-h-ref-marker" style={{ left: `${hvPct}%` }} title={`HV: ${quote.hv_20d.toFixed(1)}%`} />
                )}
              </div>
              <span className="iv-h-value">{quote.current_iv != null ? `${quote.current_iv.toFixed(1)}%` : '—'}</span>
            </div>
            <div className="iv-h-row">
              <span className="iv-h-label">HV</span>
              <div className="iv-h-track">
                <div className="iv-h-fill fill-blue" style={{ width: `${hvPct}%` }} />
                {quote.current_iv != null && (
                  <div className="iv-h-ref-marker marker-cyan" style={{ left: `${ivPct}%` }} title={`IV: ${quote.current_iv.toFixed(1)}%`} />
                )}
              </div>
              <span className="iv-h-value">{quote.hv_20d != null ? `${quote.hv_20d.toFixed(1)}%` : '—'}</span>
            </div>
            <div className="iv-h-scale">
              <span>0%</span>
              <span>{Math.ceil(maxIV / 10) * 10}%</span>
            </div>
          </div>
        </div>

        {/* IV Rank & Percentile */}
        <div className="metric-card">
          <div className="metric-label">IV Rank / Percentile</div>
          <div className="metric-value">
            {quote.iv_rank != null ? `${quote.iv_rank.toFixed(0)}%` : '—'}
          </div>
          {quote.iv_rank != null && (
            <>
              <div className="range-bar">
                <div
                  className={`range-bar-fill ${quote.iv_rank >= 70 ? 'fill-red' : quote.iv_rank >= 30 ? 'fill-cyan' : 'fill-blue'}`}
                  style={{ width: `${quote.iv_rank}%` }}
                />
                <div
                  className="range-bar-marker"
                  style={{ left: `${quote.iv_rank}%` }}
                />
              </div>
              <div className="range-bar-labels">
                <span>Low</span>
                <span>High</span>
              </div>
            </>
          )}
          <div className="iv-rank-sub">
            <div className="iv-rank-stat">
              <span className="iv-rank-stat-label">IV Rank</span>
              <span className="iv-rank-stat-value">{quote.iv_rank != null ? `${quote.iv_rank.toFixed(1)}%` : '—'}</span>
            </div>
            <div className="iv-rank-stat">
              <span className="iv-rank-stat-label">IV Percentile</span>
              <span className="iv-rank-stat-value">{quote.iv_percentile != null ? `${quote.iv_percentile.toFixed(1)}%` : '—'}</span>
            </div>
            <div className="iv-rank-stat">
              <span className="iv-rank-stat-label">IV/HV Ratio</span>
              <span className="iv-rank-stat-value">{quote.iv_hv_ratio != null ? `${quote.iv_hv_ratio.toFixed(2)}x` : '—'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
