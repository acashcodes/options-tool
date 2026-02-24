import { useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, ReferenceLine,
  ResponsiveContainer, Tooltip,
} from 'recharts';
import { getRecommendations } from '../api/client';

export default function StrategyRecommender({ quote, onLoadStrategy }) {
  const defaultDate = new Date();
  defaultDate.setDate(defaultDate.getDate() + 30);

  const [targetPrice, setTargetPrice] = useState('');
  const [targetDate, setTargetDate] = useState(defaultDate.toISOString().split('T')[0]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [direction, setDirection] = useState(null);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!quote || !targetPrice || !targetDate) return;

    setLoading(true);
    setError('');
    setResults(null);
    setDirection(null);
    try {
      const data = await getRecommendations({
        ticker: quote.symbol,
        target_price: parseFloat(targetPrice),
        target_date: targetDate,
      });
      setResults(data.recommendations);
      setDirection(data.direction);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (!quote) return null;

  const impliedMove = targetPrice
    ? (((parseFloat(targetPrice) - quote.price) / quote.price) * 100).toFixed(1)
    : null;

  return (
    <div className="recommender-section">
      <h2>Strategy Recommender</h2>
      <p className="recommender-subtitle">
        Enter your price target and date to get ranked strategy recommendations.
      </p>

      <form className="recommender-form" onSubmit={handleSubmit}>
        <div className="rec-form-row">
          <label className="rec-field">
            <span className="rec-field-label">Target Price</span>
            <div className="rec-price-input-wrap">
              <span className="rec-dollar">$</span>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder={quote.price.toFixed(2)}
                value={targetPrice}
                onChange={e => setTargetPrice(e.target.value)}
                required
              />
              {impliedMove && (
                <span className={`rec-implied-move ${parseFloat(impliedMove) >= 0 ? 'text-green' : 'text-red'}`}>
                  {parseFloat(impliedMove) >= 0 ? '+' : ''}{impliedMove}%
                </span>
              )}
            </div>
          </label>
          <label className="rec-field">
            <span className="rec-field-label">Target Date</span>
            <input
              type="date"
              value={targetDate}
              onChange={e => setTargetDate(e.target.value)}
              required
            />
          </label>
          <div className="rec-field rec-submit-field">
            <button
              type="submit"
              className="btn-recommend"
              disabled={loading || !targetPrice || !targetDate}
            >
              {loading ? (
                <><span className="spinner" /> Scanning...</>
              ) : (
                'Find Strategies'
              )}
            </button>
          </div>
        </div>
      </form>

      {direction && (
        <div className={`rec-direction-badge direction-${direction}`}>
          {direction === 'bullish' ? '\u2191' : direction === 'bearish' ? '\u2193' : '\u2194'}
          {' '}{direction.charAt(0).toUpperCase() + direction.slice(1)} bias
          {impliedMove && <span className="rec-direction-move"> ({parseFloat(impliedMove) >= 0 ? '+' : ''}{impliedMove}%)</span>}
        </div>
      )}

      {error && <div className="error-msg">{error}</div>}

      {results && results.length === 0 && (
        <div className="rec-empty">
          No viable strategies found for this target. Try adjusting your price target or date.
        </div>
      )}

      {results && results.length > 0 && (
        <div className="rec-results">
          <div className="rec-results-header">
            <span className="rec-results-count">{results.length} strategies ranked by risk-reward</span>
            <span className="rec-results-exp">Expiry: {results[0].expiration}</span>
          </div>
          {results.map((rec, i) => (
            <RecommendationCard
              key={i}
              rec={rec}
              rank={i + 1}
              onLoad={() => onLoadStrategy(rec.legs)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RecommendationCard({ rec, rank, onLoad }) {
  const isCredit = rec.net_premium > 0;

  const curveData = rec.curve.map(d => ({
    price: d.price,
    profit: d.pl > 0 ? d.pl : 0,
    loss: d.pl < 0 ? d.pl : 0,
    pl: d.pl,
  }));

  const payoffPct = rec.capital_required > 0
    ? ((rec.payoff_at_target / rec.capital_required) * 100).toFixed(1)
    : null;

  return (
    <div className="rec-card">
      <div className="rec-card-header">
        <div className="rec-rank">#{rank}</div>
        <div className="rec-card-title">
          <span className="rec-name">{rec.name}</span>
          <span className="rec-legs-summary">
            {rec.legs.map((l, i) => (
              <span key={i} className={`rec-leg-tag ${l.action === 'buy' ? 'tag-buy' : 'tag-sell'}`}>
                {l.action === 'buy' ? 'B' : 'S'} {l.type} ${l.strike}
              </span>
            ))}
          </span>
        </div>
        <div className="rec-rr-badge">
          <span className={rrColor(rec.risk_reward)}>{rec.risk_reward}x</span>
        </div>
      </div>

      <div className="rec-legs-detail">
        {rec.legs.map((l, i) => (
          <div key={i} className={`rec-leg-detail ${l.action === 'buy' ? 'leg-buy' : 'leg-sell'}`}>
            <span className="rec-leg-action">{l.action === 'buy' ? 'Buy' : 'Sell'}</span>
            <span className="rec-leg-desc">{l.type} ${l.strike}</span>
            <span className="rec-leg-exp">{l.expiration}</span>
            <span className="rec-leg-price">
              {l.bid != null && l.ask != null
                ? `$${l.bid.toFixed(2)}-${l.ask.toFixed(2)}`
                : `Mid $${l.premium.toFixed(2)}`}
            </span>
          </div>
        ))}
      </div>

      <div className="rec-card-body">
        <div className="rec-chart">
          <ResponsiveContainer width="100%" height={80}>
            <AreaChart data={curveData} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
              <defs>
                <linearGradient id={`profitFill-${rank}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00d4aa" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#00d4aa" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id={`lossFill-${rank}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff4757" stopOpacity={0.02} />
                  <stop offset="100%" stopColor="#ff4757" stopOpacity={0.25} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="profit" stroke="#00d4aa" fill={`url(#profitFill-${rank})`} strokeWidth={1.5} dot={false} />
              <Area type="monotone" dataKey="loss" stroke="#ff4757" fill={`url(#lossFill-${rank})`} strokeWidth={1.5} dot={false} />
              <ReferenceLine y={0} stroke="#444" strokeDasharray="2 2" />
              <ReferenceLine x={rec.current_price} stroke="#2563eb" strokeDasharray="2 2" strokeWidth={1} />
              <XAxis dataKey="price" hide />
              <YAxis hide />
              <Tooltip content={<MiniTooltip />} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="rec-metrics">
          <div className="rec-metric">
            <span className="rec-metric-label">Payoff at Target</span>
            <span className={`rec-metric-value ${rec.payoff_at_target >= 0 ? 'text-green' : 'text-red'}`}>
              {fmtDollar(rec.payoff_at_target)}
              {payoffPct && <span className="rec-pct"> (+{payoffPct}%)</span>}
            </span>
          </div>
          <div className="rec-metric">
            <span className="rec-metric-label">Risk/Reward <span className="rec-hint">(higher = better)</span></span>
            <span className={`rec-metric-value ${rrColor(rec.risk_reward)}`}>
              {rec.risk_reward}x
            </span>
          </div>
          <div className="rec-metric">
            <span className="rec-metric-label">Capital Required</span>
            <span className="rec-metric-value">
              {fmtDollar(rec.capital_required)}
            </span>
          </div>
          <div className="rec-metric">
            <span className="rec-metric-label">{isCredit ? 'Credit Received' : 'Net Debit'}</span>
            <span className={`rec-metric-value ${isCredit ? 'text-green' : 'text-red'}`}>
              {fmtDollar(Math.abs(rec.net_premium))}
            </span>
          </div>
          {rec.breakevens && rec.breakevens.length > 0 && (
            <div className="rec-metric">
              <span className="rec-metric-label">Breakeven{rec.breakevens.length > 1 ? 's' : ''}</span>
              <span className="rec-metric-value">
                {rec.breakevens.map(b => `$${b.toFixed(2)}`).join(', ')}
              </span>
            </div>
          )}
          <div className="rec-metric">
            <span className="rec-metric-label">Max Profit</span>
            <span className="rec-metric-value text-green">
              {rec.max_profit == null ? 'Unlimited' : fmtDollar(rec.max_profit)}
            </span>
          </div>
          <div className="rec-metric">
            <span className="rec-metric-label">Max Loss</span>
            <span className="rec-metric-value text-red">
              {fmtDollar(rec.max_loss)}
            </span>
          </div>
        </div>
      </div>

      <div className="rec-card-footer">
        <span className="rec-strategy-type">{rec.strategy_type}</span>
        <button className="btn-load-strategy" onClick={onLoad}>
          Load into Builder
        </button>
      </div>
    </div>
  );
}

function MiniTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="rec-tooltip">
      <span>${d.price.toFixed(2)}</span>
      <span className={d.pl >= 0 ? 'text-green' : 'text-red'}>
        {d.pl >= 0 ? '+' : ''}{fmtDollar(d.pl)}
      </span>
    </div>
  );
}

function rrColor(rr) {
  if (rr == null) return 'text-green';
  if (rr >= 2) return 'text-green';
  if (rr >= 1) return 'text-yellow';
  return 'text-red';
}

function fmtDollar(v) {
  if (v == null) return '\u2014';
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : v > 0 ? '+' : '';
  return `${sign}$${abs.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}
