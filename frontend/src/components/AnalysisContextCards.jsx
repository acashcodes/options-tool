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
  const metrics = portfolio?.metrics;
  const dayPnlPct = metrics?.day_pnl_percent;
  const totalPnlPct = metrics?.total_pnl_percent;

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
        <div className="context-card-label">Portfolio</div>
        <div className="context-card-body">
          {portfolio ? (
            <>
              {dayPnlPct != null ? (
                <>
                  <div className={`context-card-hero ${dayPnlPct >= 0 ? 'color-green' : 'color-red'}`}>
                    {dayPnlPct >= 0 ? '+' : ''}{dayPnlPct.toFixed(2)}%
                  </div>
                  <div className="context-card-detail">today</div>
                </>
              ) : totalPnlPct != null ? (
                <>
                  <div className={`context-card-hero ${totalPnlPct >= 0 ? 'color-green' : 'color-red'}`}>
                    {totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(2)}%
                  </div>
                  <div className="context-card-detail">total return</div>
                </>
              ) : (
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
