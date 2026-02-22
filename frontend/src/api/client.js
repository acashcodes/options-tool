const BASE = '/api';

function extractError(body, status) {
  const d = body.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map(e => e.msg || JSON.stringify(e)).join('; ');
  if (d) return JSON.stringify(d);
  return `Request failed: ${status}`;
}

async function request(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractError(body, res.status));
  }
  return res.json();
}

async function requestPost(path, data) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractError(body, res.status));
  }
  return res.json();
}

async function requestPut(path, data) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractError(body, res.status));
  }
  return res.json();
}

async function requestDelete(path) {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractError(body, res.status));
  }
  return res.json();
}

async function requestUpload(path, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ===== Market Data =====

export function getQuote(symbol) {
  return request(`/quote/${encodeURIComponent(symbol)}`);
}

export function getOptionsExpirations(symbol) {
  return request(`/options/expirations/${encodeURIComponent(symbol)}`);
}

export function getOptionsChain(symbol, expiration) {
  return request(`/options/chain/${encodeURIComponent(symbol)}?expiration=${encodeURIComponent(expiration)}`);
}

export function getHistory(symbol, period = '1y', interval = '1d') {
  return request(`/history/${encodeURIComponent(symbol)}?period=${period}&interval=${interval}`);
}

// ===== Portfolio =====

export function getPositions() {
  return request('/portfolio/positions');
}

export function addPosition(data) {
  return requestPost('/portfolio/positions', data);
}

export function updatePosition(id, data) {
  return requestPut(`/portfolio/positions/${encodeURIComponent(id)}`, data);
}

export function deletePosition(id) {
  return requestDelete(`/portfolio/positions/${encodeURIComponent(id)}`);
}

export function getEnrichedPortfolio() {
  return request('/portfolio/enriched');
}

export function getPortfolioRisk() {
  return request('/portfolio/risk');
}

export function uploadCSV(file) {
  return requestUpload('/portfolio/import/csv', file);
}

export function confirmImport(rows) {
  return requestPost('/portfolio/import/confirm', rows);
}

export function uploadOCR(file) {
  return requestUpload('/portfolio/import/ocr', file);
}

// ===== Dashboard =====

export function getMarketOverview() {
  return request('/dashboard/overview');
}

export function getWatchlist() {
  return request('/dashboard/watchlist');
}

export function addWatchlistTicker(ticker) {
  return requestPost('/dashboard/watchlist', { ticker });
}

export function removeWatchlistTicker(ticker) {
  return requestDelete(`/dashboard/watchlist/${encodeURIComponent(ticker)}`);
}

export function getEnrichedWatchlist() {
  return request('/dashboard/watchlist/enriched');
}

export function getDashboardAlerts() {
  return request('/dashboard/alerts');
}

export function dismissAlert(alertId) {
  return requestPost('/dashboard/alerts/dismiss', { alert_id: alertId });
}

export function restoreAlert(alertId) {
  return requestPost('/dashboard/alerts/restore', { alert_id: alertId });
}

export function clearDismissedAlerts() {
  return requestDelete('/dashboard/alerts/dismissed');
}

export function getAlertThresholds() {
  return request('/dashboard/alerts/thresholds');
}

export function updateAlertThresholds(thresholds) {
  return requestPut('/dashboard/alerts/thresholds', thresholds);
}

export function getDashboardNews() {
  return request('/dashboard/news');
}

// ===== Newsletter =====

export function getNewsletterLatest() {
  return request('/newsletter/latest');
}

export function getNewsletterIssue(issueId) {
  return request(`/newsletter/issues/${encodeURIComponent(issueId)}`);
}

export function getNewsletterHistory(limit = 50, offset = 0) {
  return request(`/newsletter/history?limit=${limit}&offset=${offset}`);
}

export function markNewsletterRead(issueId) {
  return requestPost('/newsletter/mark_read', { issue_id: issueId });
}

export function syncNewsletter() {
  return requestPost('/newsletter/sync_now', {});
}

// ===== Strategy Analysis =====

export function analyzeStrategy(payload) {
  return requestPost('/strategy/analyze', payload);
}

export function getAssumptions() {
  return request('/assumptions');
}

// ===== Strategy Recommender =====

export function getRecommendations(params) {
  return requestPost('/recommend', params);
}
