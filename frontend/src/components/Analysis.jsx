import { useState, useEffect, useCallback } from 'react';
import TickerSearch from './TickerSearch';
import StockInfoBar from './StockInfoBar';
import OptionsChain from './OptionsChain';

export default function Analysis({ preloadTicker, onTickerLoaded }) {
  const [quote, setQuote] = useState(null);

  const handleQuoteLoaded = useCallback((q) => {
    setQuote(q);
  }, []);

  useEffect(() => {
    if (preloadTicker) {
      onTickerLoaded?.();
    }
  }, [preloadTicker, onTickerLoaded]);

  return (
    <div className="analysis-page">
      <TickerSearch
        preloadTicker={preloadTicker}
        onQuoteLoaded={handleQuoteLoaded}
      />
      {quote && (
        <>
          <StockInfoBar quote={quote} />
          <OptionsChain symbol={quote.symbol} currentPrice={quote.price} />
        </>
      )}
    </div>
  );
}
