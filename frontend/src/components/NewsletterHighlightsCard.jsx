import { useState } from 'react';

export default function NewsletterHighlightsCard({ newsletter, onViewIssue, onViewHistory, onDelete }) {
  const [detailsExpanded, setDetailsExpanded] = useState(false);

  if (!newsletter) return null;

  const {
    id,
    headline,
    source_name,
    received_at,
    web_url,
    summary_lines = [],
    context_bullets = [],
    portfolio_bullets = [],
    watchlist_bullets = [],
    read,
  } = newsletter;

  const hasSummary = summary_lines.length > 0;
  const hasPortfolio = portfolio_bullets.length > 0;
  const hasWatchlist = watchlist_bullets.length > 0;
  const hasDetails = hasPortfolio || hasWatchlist;

  function handleHeadlineClick() {
    if (web_url) {
      window.open(web_url, '_blank', 'noopener,noreferrer');
    } else if (id && onViewIssue) {
      onViewIssue(id);
    }
  }

  return (
    <div className={`newsletter-card ${read ? '' : 'newsletter-unread'}`}>
      <div className="newsletter-card-header">
        <span className="newsletter-source">{source_name || 'Newsletter'}</span>
        <div className="newsletter-header-right">
          <span className="newsletter-date">{formatDate(received_at)}</span>
          {onDelete && (
            <button
              className="newsletter-delete-btn"
              onClick={(e) => { e.stopPropagation(); onDelete(id); }}
              title="Delete this summary"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      <div
        className={`newsletter-headline ${web_url ? 'newsletter-headline-link' : ''}`}
        onClick={handleHeadlineClick}
        title={web_url ? 'Open full issue' : ''}
      >
        {headline}
      </div>

      {/* Condensed summary lines (3-5 industry-relevant takeaways) */}
      {hasSummary && (
        <div className="newsletter-summary">
          {summary_lines.map((line, i) => (
            <p key={i} className="newsletter-summary-line">{line}</p>
          ))}
        </div>
      )}

      {/* Fallback: context bullets only if no summary available */}
      {!hasSummary && context_bullets.length > 0 && (
        <div className="newsletter-section">
          <ul className="newsletter-bullets">
            {context_bullets.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Expandable ticker details (portfolio + watchlist mentions) */}
      {hasDetails && (
        <div className="newsletter-section">
          <button
            className={`newsletter-section-toggle ${detailsExpanded ? 'expanded' : ''}`}
            onClick={() => setDetailsExpanded(!detailsExpanded)}
          >
            <span className="newsletter-section-icon">&#9656;</span>
            Ticker Mentions ({portfolio_bullets.length + watchlist_bullets.length})
          </button>
          {detailsExpanded && (
            <>
              {hasPortfolio && (
                <ul className="newsletter-bullets newsletter-bullets-portfolio">
                  {portfolio_bullets.map((b, i) => (
                    <li key={`p-${i}`}>{b}</li>
                  ))}
                </ul>
              )}
              {hasWatchlist && (
                <ul className="newsletter-bullets newsletter-bullets-watchlist">
                  {watchlist_bullets.map((b, i) => (
                    <li key={`w-${i}`}>{b}</li>
                  ))}
                </ul>
              )}
            </>
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
        {onViewHistory && (
          <button className="newsletter-action-btn" onClick={() => onViewHistory()}>
            History
          </button>
        )}
      </div>
    </div>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return '';
  }
}
