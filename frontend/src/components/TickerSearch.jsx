import { useState, useEffect, useRef } from 'react';
import { getQuote } from '../api/client';

export default function TickerSearch({ preloadTicker, onQuoteLoaded }) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const didPreload = useRef(false);

  async function fetchTicker(symbol) {
    setLoading(true);
    setError(null);
    try {
      const quote = await getQuote(symbol);
      onQuoteLoaded(quote);
    } catch (err) {
      setError(err.message);
      onQuoteLoaded(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (preloadTicker && !didPreload.current) {
      didPreload.current = true;
      setInput(preloadTicker.toUpperCase());
      fetchTicker(preloadTicker);
    }
  }, [preloadTicker]);

  function handleSubmit(e) {
    e.preventDefault();
    const symbol = input.trim();
    if (!symbol) return;
    fetchTicker(symbol);
  }

  return (
    <div className="ticker-search">
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          placeholder="Enter ticker symbol..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? 'Loading...' : 'Analyze'}
        </button>
      </form>
      {error && <div className="error-msg">{error}</div>}
    </div>
  );
}
