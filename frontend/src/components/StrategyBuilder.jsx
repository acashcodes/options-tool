import { useState } from 'react';
import { getOptionsExpirations, getOptionsChain } from '../api/client';

const TEMPLATES = [
  {
    label: 'Custom', value: 'custom',
    desc: 'Build your own strategy by clicking options in the chain above.',
    legs: '',
  },
  {
    label: 'Long Call', value: 'long_call',
    desc: 'Bullish bet with unlimited upside and limited downside. You profit if the stock rises above the strike + premium paid.',
    legs: 'Buy 1 ATM call',
  },
  {
    label: 'Long Put', value: 'long_put',
    desc: 'Bearish bet. You profit if the stock falls below the strike minus premium paid. Limited risk, high reward if the stock drops.',
    legs: 'Buy 1 ATM put',
  },
  {
    label: 'Covered Call', value: 'covered_call',
    desc: 'Income strategy: Buy 100 shares and sell a call against them. Caps your upside but generates premium income.',
    legs: 'Buy 100 shares + Sell 1 OTM call',
  },
  {
    label: 'Collar', value: 'collar',
    desc: 'Protective strategy: Buy 100 shares, buy a put for downside protection, sell a call to offset the put cost.',
    legs: 'Buy 100 shares + Buy 1 OTM put + Sell 1 OTM call',
  },
  {
    label: 'Bull Call Spread', value: 'bull_call_spread',
    desc: 'Moderately bullish with capped risk and reward. Cheaper than a long call because the sold call offsets the cost.',
    legs: 'Buy 1 ATM call + Sell 1 higher-strike call (same expiry)',
  },
  {
    label: 'Bear Put Spread', value: 'bear_put_spread',
    desc: 'Moderately bearish with capped risk and reward. Cheaper than a long put because the sold put offsets the cost.',
    legs: 'Buy 1 ATM put + Sell 1 lower-strike put (same expiry)',
  },
  {
    label: 'Bull Put Spread', value: 'bull_put_spread',
    desc: 'Credit spread that profits if the stock stays above the short put strike. Collect premium upfront with defined risk.',
    legs: 'Sell 1 ATM put + Buy 1 lower-strike put (same expiry)',
  },
  {
    label: 'Bear Call Spread', value: 'bear_call_spread',
    desc: 'Credit spread that profits if the stock stays below the short call strike. Collect premium upfront with defined risk.',
    legs: 'Sell 1 ATM call + Buy 1 higher-strike call (same expiry)',
  },
  {
    label: 'Long Straddle', value: 'long_straddle',
    desc: 'Bet on a big move in either direction. You profit if the stock moves far enough from the strike to overcome the premium paid.',
    legs: 'Buy 1 ATM call + Buy 1 ATM put (same strike, same expiry)',
  },
  {
    label: 'Long Strangle', value: 'long_strangle',
    desc: 'Similar to a straddle but cheaper — you need a bigger move to profit. Uses OTM options on both sides.',
    legs: 'Buy 1 OTM call + Buy 1 OTM put (different strikes, same expiry)',
  },
  {
    label: 'Short Straddle', value: 'short_straddle',
    desc: 'Bet on low volatility. Collect premium from both sides. You profit if the stock stays near the strike. Unlimited risk.',
    legs: 'Sell 1 ATM call + Sell 1 ATM put (same strike, same expiry)',
  },
  {
    label: 'Short Strangle', value: 'short_strangle',
    desc: 'Wider version of a short straddle. Profit zone is larger but premium collected is smaller. Unlimited risk.',
    legs: 'Sell 1 OTM call + Sell 1 OTM put (different strikes, same expiry)',
  },
  {
    label: 'Iron Condor', value: 'iron_condor',
    desc: 'Defined-risk neutral strategy. Profits if the stock stays within a range. Combines a bull put spread and bear call spread.',
    legs: 'Buy 1 low put + Sell 1 higher put + Sell 1 lower call + Buy 1 higher call',
  },
  {
    label: 'Iron Butterfly', value: 'iron_butterfly',
    desc: 'Like an iron condor but with the short strikes at the same price. Higher max profit, narrower profit zone.',
    legs: 'Buy 1 OTM put + Sell 1 ATM put + Sell 1 ATM call + Buy 1 OTM call',
  },
  {
    label: 'Calendar Spread', value: 'calendar_spread',
    desc: 'Sell a near-term call and buy the same strike call at a later expiration. Profits from time decay differential. Best when you expect the stock to stay near the strike.',
    legs: 'Sell 1 ATM call (near-term) + Buy 1 ATM call (later expiry)',
  },
];

function generateTemplateLegs(template, currentPrice, chain, expiration) {
  if (!chain || !currentPrice || !expiration) return [];

  const calls = chain.calls || [];
  const puts = chain.puts || [];

  function nearestStrike(opts, target) {
    if (!opts.length) return null;
    return opts.reduce((best, o) =>
      Math.abs(o.strike - target) < Math.abs(best.strike - target) ? o : best
    );
  }

  function mid(opt) {
    if (opt.bid != null && opt.ask != null) return +((opt.bid + opt.ask) / 2).toFixed(2);
    return opt.last_price || 0;
  }

  function leg(type, strike, action, opt) {
    return {
      type, strike, expiration, action, quantity: 1,
      premium: mid(opt), bid: opt.bid, ask: opt.ask, iv: opt.implied_volatility,
    };
  }

  const atm = currentPrice;
  const otmCallTarget = atm * 1.05;
  const otmPutTarget = atm * 0.95;
  const wingUp = atm * 1.10;
  const wingDown = atm * 0.90;

  switch (template) {
    case 'long_call': {
      const c = nearestStrike(calls, atm);
      return c ? [leg('Call', c.strike, 'buy', c)] : [];
    }
    case 'long_put': {
      const p = nearestStrike(puts, atm);
      return p ? [leg('Put', p.strike, 'buy', p)] : [];
    }
    case 'covered_call': {
      const c = nearestStrike(calls, otmCallTarget);
      if (!c) return [];
      return [
        { instrument: 'stock', action: 'buy', quantity: 100, entry_price: currentPrice, premium: currentPrice },
        leg('Call', c.strike, 'sell', c),
      ];
    }
    case 'collar': {
      const c = nearestStrike(calls, otmCallTarget);
      const p = nearestStrike(puts, otmPutTarget);
      if (!c || !p) return [];
      return [
        { instrument: 'stock', action: 'buy', quantity: 100, entry_price: currentPrice, premium: currentPrice },
        leg('Put', p.strike, 'buy', p),
        leg('Call', c.strike, 'sell', c),
      ];
    }
    case 'bull_call_spread': {
      const buy = nearestStrike(calls, atm);
      const sell = nearestStrike(calls, otmCallTarget);
      if (!buy || !sell || buy.strike === sell.strike) return [];
      return [leg('Call', buy.strike, 'buy', buy), leg('Call', sell.strike, 'sell', sell)];
    }
    case 'bear_put_spread': {
      const buy = nearestStrike(puts, atm);
      const sell = nearestStrike(puts, otmPutTarget);
      if (!buy || !sell || buy.strike === sell.strike) return [];
      return [leg('Put', buy.strike, 'buy', buy), leg('Put', sell.strike, 'sell', sell)];
    }
    case 'bull_put_spread': {
      const sell = nearestStrike(puts, atm);
      const buy = nearestStrike(puts, otmPutTarget);
      if (!buy || !sell || buy.strike === sell.strike) return [];
      return [leg('Put', sell.strike, 'sell', sell), leg('Put', buy.strike, 'buy', buy)];
    }
    case 'bear_call_spread': {
      const sell = nearestStrike(calls, atm);
      const buy = nearestStrike(calls, otmCallTarget);
      if (!buy || !sell || buy.strike === sell.strike) return [];
      return [leg('Call', sell.strike, 'sell', sell), leg('Call', buy.strike, 'buy', buy)];
    }
    case 'long_straddle': {
      const c = nearestStrike(calls, atm);
      const p = nearestStrike(puts, atm);
      if (!c || !p) return [];
      return [leg('Call', c.strike, 'buy', c), leg('Put', p.strike, 'buy', p)];
    }
    case 'long_strangle': {
      const c = nearestStrike(calls, otmCallTarget);
      const p = nearestStrike(puts, otmPutTarget);
      if (!c || !p) return [];
      return [leg('Call', c.strike, 'buy', c), leg('Put', p.strike, 'buy', p)];
    }
    case 'short_straddle': {
      const c = nearestStrike(calls, atm);
      const p = nearestStrike(puts, atm);
      if (!c || !p) return [];
      return [leg('Call', c.strike, 'sell', c), leg('Put', p.strike, 'sell', p)];
    }
    case 'short_strangle': {
      const c = nearestStrike(calls, otmCallTarget);
      const p = nearestStrike(puts, otmPutTarget);
      if (!c || !p) return [];
      return [leg('Call', c.strike, 'sell', c), leg('Put', p.strike, 'sell', p)];
    }
    case 'iron_condor': {
      const sellPut = nearestStrike(puts, otmPutTarget);
      const buyPut = nearestStrike(puts, wingDown);
      const sellCall = nearestStrike(calls, otmCallTarget);
      const buyCall = nearestStrike(calls, wingUp);
      if (!sellPut || !buyPut || !sellCall || !buyCall) return [];
      return [
        leg('Put', buyPut.strike, 'buy', buyPut),
        leg('Put', sellPut.strike, 'sell', sellPut),
        leg('Call', sellCall.strike, 'sell', sellCall),
        leg('Call', buyCall.strike, 'buy', buyCall),
      ];
    }
    case 'iron_butterfly': {
      const sellCall = nearestStrike(calls, atm);
      const sellPut = nearestStrike(puts, atm);
      const buyPut = nearestStrike(puts, otmPutTarget);
      const buyCall = nearestStrike(calls, otmCallTarget);
      if (!sellCall || !sellPut || !buyPut || !buyCall) return [];
      return [
        leg('Put', buyPut.strike, 'buy', buyPut),
        leg('Put', sellPut.strike, 'sell', sellPut),
        leg('Call', sellCall.strike, 'sell', sellCall),
        leg('Call', buyCall.strike, 'buy', buyCall),
      ];
    }
    default:
      return [];
  }
}

async function generateCalendarSpreadLegs(symbol, currentPrice, currentChain, currentExpiry) {
  if (!currentPrice || !currentExpiry) return [];

  try {
    const data = await getOptionsExpirations(symbol);
    const expirations = data.expirations || [];
    const currentIdx = expirations.indexOf(currentExpiry);
    if (currentIdx === -1 || currentIdx >= expirations.length - 1) return [];

    // Pick a back-month expiry ~30 days after the front-month
    const frontDate = new Date(currentExpiry + 'T00:00:00');
    let backExpiry = expirations[currentIdx + 1];
    for (let i = currentIdx + 1; i < expirations.length; i++) {
      const d = new Date(expirations[i] + 'T00:00:00');
      if ((d - frontDate) / 86400000 >= 25) {
        backExpiry = expirations[i];
        break;
      }
    }
    if (backExpiry === currentExpiry) return [];

    const backChain = await getOptionsChain(symbol, backExpiry);
    const frontCalls = currentChain?.calls || [];
    const backCalls = backChain?.calls || [];

    function nearestStrike(opts, target) {
      if (!opts.length) return null;
      return opts.reduce((best, o) =>
        Math.abs(o.strike - target) < Math.abs(best.strike - target) ? o : best
      );
    }

    function mid(opt) {
      if (opt.bid != null && opt.ask != null) return +((opt.bid + opt.ask) / 2).toFixed(2);
      return opt.last_price || 0;
    }

    const frontOpt = nearestStrike(frontCalls, currentPrice);
    const backOpt = nearestStrike(backCalls, frontOpt ? frontOpt.strike : currentPrice);
    if (!frontOpt || !backOpt) return [];

    return [
      {
        type: 'Call', strike: frontOpt.strike, expiration: currentExpiry,
        action: 'sell', quantity: 1, premium: mid(frontOpt),
        bid: frontOpt.bid, ask: frontOpt.ask, iv: frontOpt.implied_volatility,
      },
      {
        type: 'Call', strike: backOpt.strike, expiration: backExpiry,
        action: 'buy', quantity: 1, premium: mid(backOpt),
        bid: backOpt.bid, ask: backOpt.ask, iv: backOpt.implied_volatility,
      },
    ];
  } catch {
    return [];
  }
}

function fmt(n) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function StrategyBuilder({ legs, onLegsChange, currentPrice, chain, expiration, onAnalyze, onSaveToSlot, symbol }) {
  const [template, setTemplate] = useState('custom');
  const [loadingTemplate, setLoadingTemplate] = useState(false);

  const currentTemplate = TEMPLATES.find((t) => t.value === template) || TEMPLATES[0];

  async function handleTemplateChange(value) {
    setTemplate(value);
    if (value === 'custom') return;

    if (value === 'calendar_spread' && symbol) {
      setLoadingTemplate(true);
      try {
        const calendarLegs = await generateCalendarSpreadLegs(symbol, currentPrice, chain, expiration);
        if (calendarLegs.length > 0) {
          onLegsChange(calendarLegs);
        }
      } finally {
        setLoadingTemplate(false);
      }
      return;
    }

    const newLegs = generateTemplateLegs(value, currentPrice, chain, expiration);
    if (newLegs.length > 0) {
      onLegsChange(newLegs);
    }
  }

  function removeLeg(index) {
    onLegsChange(legs.filter((_, i) => i !== index));
    setTemplate('custom');
  }

  function toggleAction(index) {
    const updated = legs.map((leg, i) =>
      i === index ? { ...leg, action: leg.action === 'buy' ? 'sell' : 'buy' } : leg
    );
    onLegsChange(updated);
    setTemplate('custom');
  }

  function updateQuantity(index, qty) {
    const isStock = legs[index]?.instrument === 'stock';
    const q = Math.max(1, Math.min(isStock ? 10000 : 100, qty));
    const updated = legs.map((leg, i) =>
      i === index ? { ...leg, quantity: q } : leg
    );
    onLegsChange(updated);
  }

  function clearAll() {
    onLegsChange([]);
    setTemplate('custom');
  }

  function addStockLeg() {
    const stockLeg = {
      instrument: 'stock',
      action: 'buy',
      quantity: 100,
      entry_price: currentPrice || 0,
      premium: currentPrice || 0,
    };
    onLegsChange([...legs, stockLeg]);
    setTemplate('custom');
  }

  const netPremium = legs.reduce((sum, leg) => {
    if (leg.instrument === 'stock') {
      // Stock: buy = cash outflow, sell = inflow
      const cost = (leg.entry_price || leg.premium || 0) * leg.quantity;
      return sum + (leg.action === 'buy' ? -cost : cost);
    }
    const cost = (leg.premium || 0) * leg.quantity * 100;
    return sum + (leg.action === 'buy' ? -cost : cost);
  }, 0);

  const isDebit = netPremium < 0;

  // Compute strategy summary metrics
  let maxProfit = null, maxLoss = null, breakevens = [];
  if (legs.length > 0 && currentPrice) {
    const optionLegs = legs.filter(l => !l.instrument || l.instrument !== 'stock');
    const stockLegs = legs.filter(l => l.instrument === 'stock');

    // For single-leg or simple spreads, compute approximate max profit/loss
    if (optionLegs.length > 0) {
      // Max loss for debit strategies = net premium paid
      if (isDebit && stockLegs.length === 0) {
        maxLoss = Math.abs(netPremium);
      }
      // Max profit for credit strategies = net premium received
      if (!isDebit && stockLegs.length === 0) {
        maxProfit = Math.abs(netPremium);
      }

      // For vertical spreads (2 legs, same type, same expiry)
      if (optionLegs.length === 2 && optionLegs[0].type === optionLegs[1].type &&
          optionLegs[0].expiration === optionLegs[1].expiration) {
        const spread = Math.abs(optionLegs[0].strike - optionLegs[1].strike) * 100;
        if (isDebit) {
          maxProfit = spread - Math.abs(netPremium);
          maxLoss = Math.abs(netPremium);
        } else {
          maxProfit = Math.abs(netPremium);
          maxLoss = spread - Math.abs(netPremium);
        }
      }
    }

    // Simple breakeven for single option
    if (optionLegs.length === 1 && stockLegs.length === 0) {
      const leg = optionLegs[0];
      const prem = (leg.premium || 0);
      if (leg.type === 'Call') {
        breakevens = [+(leg.strike + (leg.action === 'buy' ? prem : -prem)).toFixed(2)];
      } else {
        breakevens = [+(leg.strike - (leg.action === 'buy' ? prem : -prem)).toFixed(2)];
      }
    }
  }

  return (
    <div className="strategy-builder">
      <div className="builder-header">
        <h2>Strategy Builder</h2>
        <div className="builder-actions">
          <select
            value={template}
            onChange={(e) => handleTemplateChange(e.target.value)}
            className="template-select"
          >
            {TEMPLATES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <button className="btn-ghost" onClick={addStockLeg}>+ Stock Leg</button>
          {legs.length > 0 && (
            <button className="btn-ghost" onClick={clearAll}>Clear All</button>
          )}
        </div>
      </div>

      {/* Strategy description card */}
      <div className="strategy-info">
        <div className="strategy-info-text">
          <span className="strategy-info-name">{currentTemplate.label}</span>
          <span className="strategy-info-desc">{currentTemplate.desc}</span>
        </div>
        {currentTemplate.legs && (
          <div className="strategy-info-legs">
            <span className="strategy-info-legs-label">Setup</span>
            <span className="strategy-info-legs-value">{currentTemplate.legs}</span>
          </div>
        )}
      </div>

      {loadingTemplate ? (
        <div className="builder-empty">
          <span className="spinner" /> Loading template...
        </div>
      ) : legs.length === 0 ? (
        <div className="builder-empty">
          Click on options in the chain above to add legs, or select a strategy template.
        </div>
      ) : (
        <>
          <div className="legs-table-wrapper">
            <table className="legs-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Strike</th>
                  <th>Expiration</th>
                  <th>Action</th>
                  <th>Qty</th>
                  <th>Premium</th>
                  <th>Cost</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {legs.map((leg, i) => {
                  const isStock = leg.instrument === 'stock';
                  let cost, costSigned;
                  if (isStock) {
                    cost = (leg.entry_price || leg.premium || 0) * leg.quantity;
                    costSigned = leg.action === 'buy' ? -cost : cost;
                  } else {
                    cost = (leg.premium || 0) * leg.quantity * 100;
                    costSigned = leg.action === 'buy' ? -cost : cost;
                  }
                  return (
                    <tr key={i}>
                      <td>
                        {isStock ? (
                          <span className="leg-type-badge type-stock">Stock</span>
                        ) : (
                          <span className={`leg-type-badge ${leg.type === 'Call' ? 'type-call' : 'type-put'}`}>
                            {leg.type}
                          </span>
                        )}
                      </td>
                      <td className="mono">{isStock ? '\u2014' : `$${fmt(leg.strike)}`}</td>
                      <td className="mono">{isStock ? '\u2014' : leg.expiration}</td>
                      <td>
                        <button
                          className={`action-toggle ${leg.action}`}
                          onClick={() => toggleAction(i)}
                        >
                          {leg.action.toUpperCase()}
                        </button>
                      </td>
                      <td>
                        <input
                          type="number"
                          min={1}
                          max={isStock ? 10000 : 100}
                          value={leg.quantity}
                          onChange={(e) => updateQuantity(i, parseInt(e.target.value) || 1)}
                          className="qty-input"
                        />
                      </td>
                      <td className="mono">
                        {isStock ? `$${fmt(leg.entry_price || leg.premium)}` : `$${fmt(leg.premium)}`}
                      </td>
                      <td className={`mono ${costSigned >= 0 ? 'text-green' : 'text-red'}`}>
                        {costSigned >= 0 ? '+' : ''}{fmt(costSigned)}
                      </td>
                      <td>
                        <button className="btn-remove" onClick={() => removeLeg(i)} title="Remove leg">
                          &times;
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="strategy-sticky-bar">
            <div className="sticky-bar-metrics">
              <div className="sticky-metric">
                <span className="sticky-label">Net {isDebit ? 'Debit' : 'Credit'}</span>
                <span className={`sticky-value ${isDebit ? 'text-red' : 'text-green'}`}>
                  ${fmt(Math.abs(netPremium))}
                </span>
              </div>
              {maxProfit != null && (
                <div className="sticky-metric">
                  <span className="sticky-label">Max Profit</span>
                  <span className="sticky-value text-green">${fmt(maxProfit)}</span>
                </div>
              )}
              {maxLoss != null && (
                <div className="sticky-metric">
                  <span className="sticky-label">Max Loss</span>
                  <span className="sticky-value text-red">${fmt(maxLoss)}</span>
                </div>
              )}
              {breakevens.length > 0 && (
                <div className="sticky-metric">
                  <span className="sticky-label">Breakeven</span>
                  <span className="sticky-value">${breakevens.join(' / $')}</span>
                </div>
              )}
            </div>
            <div className="sticky-bar-actions">
              {onSaveToSlot && legs.length > 0 && (
                <div className="save-slot-btns">
                  <button className="btn-slot" onClick={() => onSaveToSlot('A')}>A</button>
                  <button className="btn-slot" onClick={() => onSaveToSlot('B')}>B</button>
                </div>
              )}
              <button className="btn-analyze" onClick={onAnalyze} disabled={legs.length === 0}>
                Analyze Payoff
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
