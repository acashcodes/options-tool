function formatNumber(n) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatMarketCap(n) {
  if (n == null) return '—';
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

export default function StockInfoBar({ quote }) {
  const changeClass = quote.change >= 0 ? 'positive' : 'negative';
  const changeSign = quote.change >= 0 ? '+' : '';

  return (
    <div className="stock-info-bar">
      <div className="ticker-name">
        <span className="symbol">{quote.symbol}</span>
        <span className="name">{quote.name}</span>
      </div>

      <div className="price-block">
        <span className="price">${formatNumber(quote.price)}</span>
        {quote.change != null && (
          <span className={`change ${changeClass}`}>
            {changeSign}{formatNumber(quote.change)} ({changeSign}{quote.change_percent}%)
          </span>
        )}
      </div>

      <div className="divider" />

      <div className="stat">
        <span className="label">52W High</span>
        <span className="value">${formatNumber(quote.high_52w)}</span>
      </div>

      <div className="stat">
        <span className="label">52W Low</span>
        <span className="value">${formatNumber(quote.low_52w)}</span>
      </div>

      <div className="divider" />

      <div className="stat">
        <span className="label">Mkt Cap</span>
        <span className="value">{formatMarketCap(quote.market_cap)}</span>
      </div>

      <div className="stat">
        <span className="label">Volume</span>
        <span className="value">{quote.volume != null ? quote.volume.toLocaleString() : '—'}</span>
      </div>

      {quote.earnings_date && (
        <>
          <div className="divider" />
          <div className="stat">
            <span className="label">Earnings</span>
            <span className="value">{quote.earnings_date}</span>
          </div>
        </>
      )}
    </div>
  );
}
