import { useState, useEffect } from 'react';
import { getMarketOverview, getTechnicals, getDashboardAlerts, getEnrichedPortfolio } from '../api/client';

export default function AnalysisContextCards() {
  const [overview, setOverview] = useState(null);
  const [technicals, setTechnicals] = useState(null);
  const [alertData, setAlertData] = useState(null);
  const [portfolio, setPortfolio] = useState(null);

  useEffect(() => {
    // Fetch all data in parallel
    getMarketOverview().then(setOverview).catch(() => {});
    getTechnicals('SPY').then(setTechnicals).catch(() => {});
    getDashboardAlerts().then(setAlertData).catch(() => {});
    getEnrichedPortfolio().then(setPortfolio).catch(() => {});
  }, []);

  // Market Regime card data
  const vix = overview?.vix;
  const vixPrice = vix?.price;
  const regime = vixPrice != null ? (vixPrice < 15 ? 'Low Vol' : vixPrice < 20 ? 'Normal' : vixPrice < 30 ? 'Elevated' : 'High Vol') : null;
  const regimeColor = vixPrice != null ? (vixPrice < 15 ? 'color-cyan' : vixPrice < 20 ? '' : vixPrice < 30 ? 'color-amber' : 'color-red') : '';

  // SPY distance from 200 DMA
  const spy200 = technicals?.moving_averages?.find(m => m.period === 200);
  const spyDist = spy200?.pct_distance;

  // Alert data
  const activeAlerts = alertData?.active_count || 0;
  const earningsAlerts = (alertData?.alerts || []).filter(a => !a.dismissed && a.type === 'earnings').length;
  const ivAlerts = (alertData?.alerts || []).filter(a => !a.dismissed && (a.type === 'iv_high' || a.type === 'iv_low')).length;
  const expiryAlerts = (alertData?.alerts || []).filter(a => !a.dismissed && a.type === 'expiration').length;

  // Portfolio data
  const totalMV = portfolio?.total_market_value;
  const dayPnl = portfolio?.total_day_pnl;
  const positions = portfolio?.positions || [];
  const topPos = positions.length > 0 ? positions.reduce((a, b) => Math.abs(b.market_value || 0) > Math.abs(a.market_value || 0) ? b : a, positions[0]) : null;

  return (
    <div className="context-cards">
      {/* Market Regime */}
      <div className="context-card">
        <div className="context-card-label">Market Regime</div>
        <div className="context-card-body">
          {vixPrice != null ? (
            <>
              <div className="context-card-hero">
                <span className={regimeColor} style={{ fontWeight: 700 }}>{regime}</span>
              </div>
              <div className="context-card-detail">
                VIX at {vixPrice.toFixed(1)}
              </div>
              {spyDist != null && (
                <div className="context-card-detail">
                  SPY {spyDist >= 0 ? '+' : ''}{spyDist.toFixed(1)}% from 200 DMA
                </div>
              )}
            </>
          ) : (
            <span className="context-card-loading">Loading...</span>
          )}
        </div>
      </div>

      {/* Today's Activity */}
      <div className="context-card">
        <div className="context-card-label">Today's Activity</div>
        <div className="context-card-body">
          {alertData ? (
            <>
              <div className="context-card-hero">
                {activeAlerts} <span className="context-card-unit">active alerts</span>
              </div>
              {earningsAlerts > 0 && (
                <div className="context-card-detail">{earningsAlerts} earnings approaching</div>
              )}
              {ivAlerts > 0 && (
                <div className="context-card-detail">{ivAlerts} IV extreme{ivAlerts > 1 ? 's' : ''}</div>
              )}
              {expiryAlerts > 0 && (
                <div className="context-card-detail color-red">{expiryAlerts} expiring soon</div>
              )}
              {activeAlerts === 0 && (
                <div className="context-card-detail">All clear — no alerts</div>
              )}
            </>
          ) : (
            <span className="context-card-loading">Loading...</span>
          )}
        </div>
      </div>

      {/* Portfolio Snapshot */}
      <div className="context-card">
        <div className="context-card-label">Portfolio Snapshot</div>
        <div className="context-card-body">
          {portfolio ? (
            <>
              <div className="context-card-hero">
                {totalMV != null ? `$${totalMV.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
              </div>
              {dayPnl != null && (
                <div className={`context-card-detail ${dayPnl >= 0 ? 'color-cyan' : 'color-red'}`}>
                  Day P&L: {dayPnl >= 0 ? '+' : ''}{dayPnl.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })}
                </div>
              )}
              {topPos && (
                <div className="context-card-detail">
                  Top: {topPos.ticker} ({((Math.abs(topPos.market_value || 0) / (totalMV || 1)) * 100).toFixed(0)}%)
                </div>
              )}
              {positions.length === 0 && (
                <div className="context-card-detail">No positions yet</div>
              )}
            </>
          ) : (
            <span className="context-card-loading">Loading...</span>
          )}
        </div>
      </div>
    </div>
  );
}
