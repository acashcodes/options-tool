import { useState } from 'react';

export default function NewsletterHighlightsCard({ newsletter, onViewIssue, onViewHistory }) {
  const [portfolioExpanded, setPortfolioExpanded] = useState(true);
  const [watchlistExpanded, setWatchlistExpanded] = useState(false);

  if (!newsletter) return null;

  const {
    id,
    headline,
    source_name,
    received_at,
    web_url,
    context_bullets = [],
    portfolio_bullets = [],
    watchlist_bullets = [],
    read,
  } = newsletter;

  const hasPortfolio = portfolio_bullets.length > 0;
  const hasWatchlist = watchlist_bullets.length > 0;

  return (
    <div className={`newsletter-card ${read ? '' : 'newsletter-unread'}`}>
      <div className="newsletter-card-header">
        <span className="newsletter-source">{source_name || 'Newsletter'}</span>
        <span className="newsletter-time">{formatTimeAgo(received_at)}</span>
      </div>

      <div className="newsletter-headline">{headline}</div>

      {/* Context bullets */}
      {context_bullets.length > 0 && (
        <div className="newsletter-section">
          <ul className="newsletter-bullets">
            {context_bullets.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Portfolio bullets (auto-expanded) */}
      {hasPortfolio && (
        <div className="newsletter-section">
          <button
            className={`newsletter-section-toggle ${portfolioExpanded ? 'expanded' : ''}`}
            onClick={() => setPortfolioExpanded(!portfolioExpanded)}
          >
            <span className="newsletter-section-icon">&#9656;</span>
            Portfolio Mentions ({portfolio_bullets.length})
          </button>
          {portfolioExpanded && (
            <ul className="newsletter-bullets newsletter-bullets-portfolio">
              {portfolio_bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Watchlist bullets (collapsed by default) */}
      {hasWatchlist && (
        <div className="newsletter-section">
          <button
            className={`newsletter-section-toggle ${watchlistExpanded ? 'expanded' : ''}`}
            onClick={() => setWatchlistExpanded(!watchlistExpanded)}
          >
            <span className="newsletter-section-icon">&#9656;</span>
            Watchlist Mentions ({watchlist_bullets.length})
          </button>
          {watchlistExpanded && (
            <ul className="newsletter-bullets newsletter-bullets-watchlist">
              {watchlist_bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="newsletter-card-actions">
        {web_url && (
          <a
            className="newsletter-action-btn"
            href={web_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open Full Issue
          </a>
        )}
        {!web_url && id && (
          <button className="newsletter-action-btn" onClick={() => onViewIssue && onViewIssue(id)}>
            Open Full Issue
          </button>
        )}
        <button className="newsletter-action-btn" onClick={() => onViewHistory && onViewHistory()}>
          History
        </button>
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
