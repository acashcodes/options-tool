import { useState, useEffect } from 'react';
import { getMarketOverview } from '../api/client';

function fearGreedLevel(vixPrice) {
  if (vixPrice == null) return { label: '\u2014', cls: '' };
  if (vixPrice < 15) return { label: 'Extreme Greed', cls: 'fg-extreme-greed' };
  if (vixPrice < 20) return { label: 'Greed', cls: 'fg-greed' };
  if (vixPrice < 25) return { label: 'Neutral', cls: 'fg-neutral' };
  if (vixPrice < 30) return { label: 'Fear', cls: 'fg-fear' };
  return { label: 'Extreme Fear', cls: 'fg-extreme-fear' };
}

function vixColorClass(vixPrice) {
  if (vixPrice == null) return '';
  if (vixPrice < 20) return 'color-cyan';
  if (vixPrice < 25) return 'color-yellow';
  return 'color-red';
}

function OverviewItem({ label, data, valueClass, suffix, noSign }) {
  if (!data || data.price == null) {
    return (
      <div className="market-overview-item">
        <span className="overview-label">{label}</span>
        <span className="overview-price">{'\u2014'}</span>
      </div>
    );
  }

  const isPositive = data.change >= 0;
  const changeClass = isPositive ? 'color-cyan' : 'color-red';
  const sign = !noSign && isPositive ? '+' : '';

  return (
    <div className="market-overview-item">
      <span className="overview-label">{label}</span>
      <span className={`overview-price ${valueClass || ''}`}>
        {data.price.toFixed(2)}{suffix || ''}
      </span>
      {data.change != null && (
        <span className={`overview-change ${changeClass}`}>
          {sign}{data.change.toFixed(2)} ({sign}{data.change_percent?.toFixed(2)}%)
        </span>
      )}
    </div>
  );
}

export default function MarketOverviewBar() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMarketOverview()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="market-overview-bar">
        <span className="market-overview-loading">
          <span className="spinner" /> Loading market data...
        </span>
      </div>
    );
  }

  if (!data) return null;

  const fg = fearGreedLevel(data.vix?.price);

  return (
    <div className="market-overview-bar">
      <OverviewItem label="S&P 500" data={data.spy} />
      <OverviewItem label="NASDAQ" data={data.qqq} />
      <OverviewItem
        label="VIX"
        data={data.vix}
        valueClass={vixColorClass(data.vix?.price)}
        noSign
      />
      <OverviewItem label="10Y Yield" data={data.tnx} suffix="%" noSign />
      <div className={`market-overview-item fg-item`}>
        <span className="overview-label">Fear & Greed</span>
        <span className={`overview-fg-value ${fg.cls}`}>{fg.label}</span>
      </div>
    </div>
  );
}
