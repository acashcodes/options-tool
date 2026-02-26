import { useState, useEffect } from 'react';
import {
  getDashboardAlerts, dismissAlert, restoreAlert,
  clearDismissedAlerts, updateAlertThresholds, getDashboardNews,
  getDashboardNewsGrouped,
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
  const [newsGrouped, setNewsGrouped] = useState(null); // { groups: [], ungrouped: [] }
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsView, setNewsView] = useState('grouped'); // 'grouped' or 'chronological'
  const [showAllAlerts, setShowAllAlerts] = useState(false);
  const [showAllNews, setShowAllNews] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState({}); // { ticker: bool }

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

  // Fetch both flat and grouped news
  function fetchNews() {
    setNewsLoading(true);
    Promise.all([
      getDashboardNews().catch(() => ({ articles: [] })),
      getDashboardNewsGrouped().catch(() => ({ groups: [], ungrouped: [] })),
    ]).then(([flatData, groupedData]) => {
      setNews(flatData.articles || []);
      setNewsGrouped(groupedData);
    }).finally(() => setNewsLoading(false));
  }

  useEffect(() => {
    fetchAlerts();
    fetchNews();
  }, []);

  function toggleGroupExpanded(ticker) {
    setExpandedGroups(prev => ({ ...prev, [ticker]: !prev[ticker] }));
  }

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


      {/* === News Feed with Grouped / Chronological toggle === */}
      <div className="news-section-block">
        <div className="news-section-header">
          <div className="news-section-label">Latest News</div>
          <div className="news-view-toggle">
            <button
              className={`news-toggle-btn ${newsView === 'grouped' ? 'active' : ''}`}
              onClick={() => setNewsView('grouped')}
            >
              Grouped
            </button>
            <button
              className={`news-toggle-btn ${newsView === 'chronological' ? 'active' : ''}`}
              onClick={() => setNewsView('chronological')}
            >
              Chronological
            </button>
          </div>
        </div>
        {newsLoading ? (
          <div className="loading"><span className="spinner" /> Loading news...</div>
        ) : newsView === 'grouped' ? (
          <GroupedNewsView
            grouped={newsGrouped}
            expandedGroups={expandedGroups}
            onToggleGroup={toggleGroupExpanded}
            showAll={showAllNews}
            onToggleShowAll={() => setShowAllNews(!showAllNews)}
          />
        ) : (
          <ChronologicalNewsView
            articles={news}
            showAll={showAllNews}
            onToggleShowAll={() => setShowAllNews(!showAllNews)}
          />
        )}
      </div>

      {/* === Big Moves in Portfolio === */}
      {bigMoves.length > 0 && (
        <div className="news-section-block">
          <div className="news-section-label">Big Moves</div>
          <div className="alerts-list">
            {bigMoves.map(alert => {
              const moveDir = alert.direction || (alert.message.includes('up') ? 'up' : 'down');
              const movePct = alert.change_percent != null ? alert.change_percent : '';
              const moveColor = moveDir === 'up' ? 'color-green' : 'color-red';
              return (
                <div
                  key={alert.id}
                  className={`alert-item alert-${alert.severity}`}
                  onClick={() => onNavigateToAnalysis(alert.ticker)}
                >
                  <span className="alert-icon">{SEVERITY_ICONS[alert.severity]}</span>
                  <span className="alert-message">
                    {alert.ticker} moved{' '}
                    <span className={moveColor} style={{ fontWeight: 700 }}>
                      {movePct}% {moveDir}
                    </span>
                    {' '}today
                  </span>
                  <span className="alert-arrow">&rarr;</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* === IV Ranks === */}
      {ivAlerts.length > 0 && (
        <div className="news-section-block">
          <div className="news-section-label">IV Ranks</div>
          <div className="alerts-list">
            {ivAlerts.map(alert => {
              const ivLevel = alert.iv_level || (alert.type === 'iv_high' ? 'high' : 'low');
              const ivRank = alert.iv_rank != null ? `${alert.iv_rank}%` : '';
              const ivColor = ivLevel === 'high' ? 'color-red' : 'color-green';
              const ivLabel = ivLevel === 'high' ? 'elevated' : 'depressed';
              return (
                <div
                  key={alert.id}
                  className={`alert-item alert-${alert.severity}`}
                  onClick={() => onNavigateToAnalysis(alert.ticker)}
                >
                  <span className="alert-icon">{SEVERITY_ICONS[alert.severity]}</span>
                  <span className="alert-type-tag">{TYPE_LABELS[alert.type]}</span>
                  <span className="alert-message">
                    {alert.ticker} IV rank at{' '}
                    <span className={ivColor} style={{ fontWeight: 700 }}>{ivRank}</span>
                    {' '}&mdash; {ivLabel}
                  </span>
                  <span className="alert-arrow">&rarr;</span>
                </div>
              );
            })}
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


function GroupedNewsView({ grouped, expandedGroups, onToggleGroup, showAll, onToggleShowAll }) {
  if (!grouped || (grouped.groups.length === 0 && grouped.ungrouped.length === 0)) {
    return <div className="alerts-empty">No news available.</div>;
  }

  const { groups, ungrouped } = grouped;
  const visibleUngrouped = showAll ? ungrouped : ungrouped.slice(0, 3);
  const totalArticles = groups.reduce((s, g) => s + g.count, 0) + ungrouped.length;

  return (
    <div className="news-grouped-view">
      {groups.map(group => {
        const isExpanded = expandedGroups[group.ticker];
        return (
          <div key={group.ticker} className="news-group-card">
            <div className="news-group-header" onClick={() => onToggleGroup(group.ticker)}>
              <span className="news-group-ticker">{group.ticker}</span>
              <span className="news-group-count">{group.count} articles</span>
              <span className={`news-group-chevron ${isExpanded ? 'expanded' : ''}`}>&#9662;</span>
            </div>
            {group.summary && (
              <div className="news-group-summary">{group.summary}</div>
            )}
            {isExpanded && (
              <div className="news-group-articles">
                {group.articles.map((article, i) => (
                  <a
                    key={i}
                    className="news-item news-item-nested"
                    href={article.link}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <span className="news-title">{article.title}</span>
                    <span className="news-meta">
                      {article.publisher}
                      {article.published && ` · ${formatTimeAgo(article.published)}`}
                    </span>
                  </a>
                ))}
              </div>
            )}
          </div>
        );
      })}
      {visibleUngrouped.length > 0 && (
        <div className="news-list">
          {visibleUngrouped.map((article, i) => (
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
                {article.published && ` · ${formatTimeAgo(article.published)}`}
              </span>
            </a>
          ))}
        </div>
      )}
      {totalArticles > 5 && (
        <button className="section-show-more" onClick={onToggleShowAll}>
          {showAll ? 'Show less' : `Show all ${totalArticles} articles`}
        </button>
      )}
    </div>
  );
}

function ChronologicalNewsView({ articles, showAll, onToggleShowAll }) {
  if (!articles || articles.length === 0) {
    return <div className="alerts-empty">No news available.</div>;
  }
  const visible = showAll ? articles : articles.slice(0, 5);
  return (
    <>
      <div className="news-list">
        {visible.map((article, i) => (
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
              {article.published && ` · ${formatTimeAgo(article.published)}`}
            </span>
          </a>
        ))}
      </div>
      {articles.length > 5 && (
        <button className="section-show-more" onClick={onToggleShowAll}>
          {showAll ? 'Show less' : `Show all ${articles.length} articles`}
        </button>
      )}
    </>
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
