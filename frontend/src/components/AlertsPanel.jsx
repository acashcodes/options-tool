import { useState, useEffect } from 'react';
import {
  getDashboardAlerts, dismissAlert, restoreAlert,
  clearDismissedAlerts, updateAlertThresholds, getDashboardNews,
} from '../api/client';

const SEVERITY_ICONS = {
  danger: '\u26A0',
  warning: '\u25CF',
  info: '\u2139',
};

const TYPE_LABELS = {
  earnings: 'Earnings',
  iv_high: 'High IV',
  iv_low: 'Low IV',
  expiration: 'Expiring',
  large_move: 'Big Move',
};

export default function AlertsPanel({ onNavigateToAnalysis }) {
  const [alerts, setAlerts] = useState([]);
  const [groups, setGroups] = useState([]);
  const [activeCount, setActiveCount] = useState(0);
  const [dismissedCount, setDismissedCount] = useState(0);
  const [thresholds, setThresholds] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showDismissed, setShowDismissed] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [news, setNews] = useState([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [showAllAlerts, setShowAllAlerts] = useState(false);
  const [showAllNews, setShowAllNews] = useState(false);

  function fetchAlerts() {
    getDashboardAlerts()
      .then((data) => {
        setAlerts(data.alerts || []);
        setGroups(data.groups || []);
        setActiveCount(data.active_count || 0);
        setDismissedCount(data.dismissed_count || 0);
        setThresholds(data.thresholds || null);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  // Fetch news on mount (show by default now)
  function fetchNews() {
    setNewsLoading(true);
    getDashboardNews()
      .then((data) => setNews(data.articles || []))
      .catch(() => {})
      .finally(() => setNewsLoading(false));
  }

  useEffect(() => {
    fetchAlerts();
    fetchNews();
  }, []);

  function handleDismiss(e, alertId) {
    e.stopPropagation();
    dismissAlert(alertId).then(() => fetchAlerts());
  }

  function handleRestore(e, alertId) {
    e.stopPropagation();
    restoreAlert(alertId).then(() => fetchAlerts());
  }

  function handleClearDismissed() {
    clearDismissedAlerts().then(() => fetchAlerts());
  }

  function handleThresholdSave(updates) {
    updateAlertThresholds(updates).then((t) => {
      setThresholds(t);
      setShowSettings(false);
      fetchAlerts();
    });
  }

  const activeAlerts = alerts.filter(a => !a.dismissed);
  const dismissedAlerts = alerts.filter(a => a.dismissed);

  // Categorize alerts into dedicated sections (no duplicates)
  const bigMoves = activeAlerts.filter(a => a.type === 'large_move');
  const ivAlerts = activeAlerts.filter(a => a.type === 'iv_high' || a.type === 'iv_low');
  const generalAlerts = activeAlerts.filter(a => a.type !== 'large_move' && a.type !== 'iv_high' && a.type !== 'iv_low');

  // Top 3 general alerts (earnings, expiration) — big moves & IV have their own sections
  const topAlerts = generalAlerts.slice(0, 3);
  const hasMoreAlerts = generalAlerts.length > 3;

  if (loading) {
    return (
      <div className="alerts-panel">
        <div className="alerts-header">
          <h3>News & Alerts</h3>
        </div>
        <div className="loading"><span className="spinner" /> Loading...</div>
      </div>
    );
  }

  return (
    <div className="alerts-panel alerts-panel-expanded">
      <div className="alerts-header">
        <h3>News & Alerts</h3>
        {activeCount > 0 && <span className="alerts-count">{activeCount}</span>}
        <div className="alerts-actions">
          <button
            className={`alerts-action-btn ${showSettings ? 'active' : ''}`}
            onClick={() => setShowSettings(!showSettings)}
            title="Alert settings"
          >
            Settings
          </button>
          {dismissedCount > 0 && (
            <button
              className={`alerts-action-btn ${showDismissed ? 'active' : ''}`}
              onClick={() => setShowDismissed(!showDismissed)}
              title={`${dismissedCount} dismissed`}
            >
              Dismissed ({dismissedCount})
            </button>
          )}
        </div>
      </div>

      {/* Threshold settings panel */}
      {showSettings && thresholds && (
        <ThresholdSettings
          thresholds={thresholds}
          onSave={handleThresholdSave}
          onClose={() => setShowSettings(false)}
        />
      )}

      {/* === Top Alerts (earnings, expiration — big moves & IV have own sections) === */}
      {topAlerts.length > 0 && (
        <div className="news-section-block">
          <div className="news-section-label">Top Alerts</div>
          <div className="alerts-list">
            {(showAllAlerts ? generalAlerts : topAlerts).map(alert => (
              <div
                key={alert.id}
                className={`alert-item alert-${alert.severity}`}
                onClick={() => onNavigateToAnalysis(alert.ticker)}
              >
                <span className="alert-icon">{SEVERITY_ICONS[alert.severity]}</span>
                <span className="alert-type-tag">{TYPE_LABELS[alert.type] || alert.type}</span>
                <span className="alert-message">{alert.message}</span>
                <button
                  className="alert-dismiss-btn"
                  onClick={(e) => handleDismiss(e, alert.id)}
                  title="Dismiss"
                >
                  &times;
                </button>
                <span className="alert-arrow">&rarr;</span>
              </div>
            ))}
          </div>
          {hasMoreAlerts && (
            <button
              className="section-show-more"
              onClick={() => setShowAllAlerts(!showAllAlerts)}
            >
              {showAllAlerts ? 'Show less' : `Show all ${generalAlerts.length} alerts`}
            </button>
          )}
        </div>
      )}

      {activeAlerts.length === 0 && (
        <div className="news-section-block">
          <div className="news-section-label">Alerts</div>
          <div className="alerts-empty">No active alerts. Looking good.</div>
        </div>
      )}


      {/* === News Feed (visible by default) === */}
      <div className="news-section-block">
        <div className="news-section-label">Latest News</div>
        {newsLoading ? (
          <div className="loading"><span className="spinner" /> Loading news...</div>
        ) : news.length === 0 ? (
          <div className="alerts-empty">No news available.</div>
        ) : (
          <>
            <div className="news-list">
              {(showAllNews ? news : news.slice(0, 5)).map((article, i) => (
                <a
                  key={i}
                  className="news-item"
                  href={article.link}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span className="news-ticker">{article.ticker}</span>
                  <span className="news-title">{article.title}</span>
                  <span className="news-meta">
                    {article.publisher}
                    {article.published && ` \u00B7 ${formatTimeAgo(article.published)}`}
                  </span>
                </a>
              ))}
            </div>
            {news.length > 5 && (
              <button
                className="section-show-more"
                onClick={() => setShowAllNews(!showAllNews)}
              >
                {showAllNews ? 'Show less' : `Show all ${news.length} articles`}
              </button>
            )}
          </>
        )}
      </div>

      {/* === Big Moves in Portfolio === */}
      {bigMoves.length > 0 && (
        <div className="news-section-block">
          <div className="news-section-label">Big Moves</div>
          <div className="alerts-list">
            {bigMoves.map(alert => (
              <div
                key={alert.id}
                className={`alert-item alert-${alert.severity}`}
                onClick={() => onNavigateToAnalysis(alert.ticker)}
              >
                <span className="alert-icon">{SEVERITY_ICONS[alert.severity]}</span>
                <span className="alert-message">{alert.message}</span>
                <span className="alert-arrow">&rarr;</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* === IV Ranks === */}
      {ivAlerts.length > 0 && (
        <div className="news-section-block">
          <div className="news-section-label">IV Ranks</div>
          <div className="alerts-list">
            {ivAlerts.map(alert => (
              <div
                key={alert.id}
                className={`alert-item alert-${alert.severity}`}
                onClick={() => onNavigateToAnalysis(alert.ticker)}
              >
                <span className="alert-icon">{SEVERITY_ICONS[alert.severity]}</span>
                <span className="alert-type-tag">{TYPE_LABELS[alert.type]}</span>
                <span className="alert-message">{alert.message}</span>
                <span className="alert-arrow">&rarr;</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dismissed alerts */}
      {showDismissed && dismissedAlerts.length > 0 && (
        <div className="dismissed-section">
          <div className="dismissed-header">
            <span>Dismissed</span>
            <button className="alerts-action-btn" onClick={handleClearDismissed}>
              Clear All
            </button>
          </div>
          <div className="alerts-list">
            {dismissedAlerts.map(alert => (
              <div
                key={alert.id}
                className={`alert-item alert-${alert.severity} alert-dismissed`}
              >
                <span className="alert-icon">{SEVERITY_ICONS[alert.severity]}</span>
                <span className="alert-message">{alert.message}</span>
                <button
                  className="alert-restore-btn"
                  onClick={(e) => handleRestore(e, alert.id)}
                  title="Restore"
                >
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function ThresholdSettings({ thresholds, onSave, onClose }) {
  const [vals, setVals] = useState({ ...thresholds });

  function handleChange(key, value) {
    setVals(prev => ({ ...prev, [key]: value }));
  }

  return (
    <div className="threshold-settings">
      <div className="threshold-row">
        <label>Earnings alert window</label>
        <div className="threshold-input-wrap">
          <input
            type="number" min="1" max="30"
            value={vals.earnings_days}
            onChange={e => handleChange('earnings_days', parseInt(e.target.value) || 7)}
          />
          <span>days</span>
        </div>
      </div>
      <div className="threshold-row">
        <label>IV rank high alert</label>
        <div className="threshold-input-wrap">
          <span>&gt;</span>
          <input
            type="number" min="50" max="100"
            value={vals.iv_high}
            onChange={e => handleChange('iv_high', parseInt(e.target.value) || 80)}
          />
          <span>%</span>
        </div>
      </div>
      <div className="threshold-row">
        <label>IV rank low alert</label>
        <div className="threshold-input-wrap">
          <span>&lt;</span>
          <input
            type="number" min="0" max="50"
            value={vals.iv_low}
            onChange={e => handleChange('iv_low', parseInt(e.target.value) || 20)}
          />
          <span>%</span>
        </div>
      </div>
      <div className="threshold-row">
        <label>Large move alert</label>
        <div className="threshold-input-wrap">
          <span>&gt;</span>
          <input
            type="number" min="1" max="20" step="0.5"
            value={vals.large_move_pct}
            onChange={e => handleChange('large_move_pct', parseFloat(e.target.value) || 3)}
          />
          <span>%</span>
        </div>
      </div>
      <div className="threshold-row">
        <label>Expiration alert window</label>
        <div className="threshold-input-wrap">
          <input
            type="number" min="1" max="30"
            value={vals.expiration_days}
            onChange={e => handleChange('expiration_days', parseInt(e.target.value) || 7)}
          />
          <span>days</span>
        </div>
      </div>
      <div className="threshold-actions">
        <button className="btn-primary btn-sm" onClick={() => onSave(vals)}>Save</button>
        <button className="btn-secondary btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}


function formatTimeAgo(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHrs = Math.floor(diffMins / 60);
    if (diffHrs < 24) return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    return `${diffDays}d ago`;
  } catch {
    return '';
  }
}
