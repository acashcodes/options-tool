const BASE = '/api';

async function request(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export function getQuote(symbol) {
  return request(`/quote/${encodeURIComponent(symbol)}`);
}

export function getOptionsExpirations(symbol) {
  return request(`/options/expirations/${encodeURIComponent(symbol)}`);
}

export function getOptionsChain(symbol, expiration) {
  return request(`/options/chain/${encodeURIComponent(symbol)}?expiration=${encodeURIComponent(expiration)}`);
}
