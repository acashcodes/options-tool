import { useState, useEffect } from 'react';
import { getNewsletterHistory, markNewsletterRead, syncNewsletter, deleteNewsletterIssue } from '../api/client';
import NewsletterHighlightsCard from './NewsletterHighlightsCard';

export default function NewsletterPanel() {
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [expanded, setExpanded] = useState(false);

  function fetchIssues() {
    setLoading(true);
    getNewsletterHistory(50)
      .then((data) => setIssues(data.issues || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => { fetchIssues(); }, []);

  function handleSync() {
    setSyncing(true);
    syncNewsletter()
      .then(() => fetchIssues())
      .catch(() => {})
      .finally(() => setSyncing(false));
  }

  function handleMarkRead(issueId) {
    markNewsletterRead(issueId).catch(() => {});
    setIssues(prev => prev.map(i => i.id === issueId ? { ...i, read: true } : i));
  }

  function handleDelete(issueId) {
    setIssues(prev => prev.filter(i => i.id !== issueId));
    deleteNewsletterIssue(issueId).catch(() => fetchIssues());
  }

  const displayIssues = expanded ? issues : issues.slice(0, 5);
  const hasMore = issues.length > 5;

  return (
    <div className="newsletter-panel">
      <div className="newsletter-panel-header">
        <h3>Newsletters</h3>
        <div className="newsletter-panel-actions">
          <button
            className="alerts-action-btn"
            onClick={handleSync}
            disabled={syncing}
            title="Fetch new emails now"
          >
            {syncing ? 'Syncing...' : 'Sync'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading"><span className="spinner" /> Loading newsletters...</div>
      ) : issues.length === 0 ? (
        <div className="newsletter-panel-empty">
          <p>No newsletters yet.</p>
          <p className="newsletter-panel-hint">
            Emails arriving in the connected inbox will be summarized here automatically.
          </p>
        </div>
      ) : (
        <>
          <div className="newsletter-issues-list">
            {displayIssues.map((issue) => (
              <NewsletterHighlightsCard
                key={issue.id}
                newsletter={issue}
                onViewIssue={() => handleMarkRead(issue.id)}
                onViewHistory={null}
                onDelete={handleDelete}
              />
            ))}
          </div>
          {hasMore && (
            <button
              className="section-show-more"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? 'Show less' : `Show all ${issues.length} newsletters`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
