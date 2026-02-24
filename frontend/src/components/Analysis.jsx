import { useState, useEffect, useCallback, useRef } from 'react';
import TickerSearch from './TickerSearch';
import StockInfoBar from './StockInfoBar';
import StockChart from './StockChart';
import OptionsChain from './OptionsChain';
import StrategyBuilder from './StrategyBuilder';
import PayoffDiagram from './PayoffDiagram';
import StrategyComparison from './StrategyComparison';
import StrategyRecommender from './StrategyRecommender';
import { getOptionsChain } from '../api/client';
import AnalysisContextCards from './AnalysisContextCards';
import OptionsAnalytics from './OptionsAnalytics';

export default function Analysis({ preloadTicker, onTickerLoaded }) {
  const [quote, setQuote] = useState(null);
  const [legs, setLegs] = useState([]);
  const [showPayoff, setShowPayoff] = useState(false);
  const [chainData, setChainData] = useState(null);
  const [chainExpiry, setChainExpiry] = useState(null);
  const [slotA, setSlotA] = useState(null);
  const [slotB, setSlotB] = useState(null);
  const builderRef = useRef(null);

  const handleQuoteLoaded = useCallback((q) => {
    setQuote(q);
    setLegs([]);
    setShowPayoff(false);
    setChainData(null);
    setChainExpiry(null);
    setSlotA(null);
    setSlotB(null);
  }, []);

  useEffect(() => {
    if (preloadTicker) {
      onTickerLoaded?.();
    }
  }, [preloadTicker, onTickerLoaded]);

  function handleAddLeg(leg) {
    setLegs((prev) => [...prev, leg]);
    setShowPayoff(false);

    if (quote && leg.expiration && leg.expiration !== chainExpiry) {
      getOptionsChain(quote.symbol, leg.expiration)
        .then((data) => {
          setChainData(data);
          setChainExpiry(leg.expiration);
        })
        .catch(() => {});
    }

    setTimeout(() => {
      builderRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 100);
  }

  function handleLegsChange(newLegs) {
    setLegs(newLegs);
    setShowPayoff(false);
  }

  function handleAnalyze() {
    setShowPayoff(true);
  }

  function handleSaveToSlot(slot) {
    const saved = { legs: [...legs] };
    if (slot === 'A') setSlotA(saved);
    else setSlotB(saved);
  }

  function handleClearComparison() {
    setSlotA(null);
    setSlotB(null);
  }

  function handleLoadRecommendation(recLegs) {
    setLegs(recLegs);
    setShowPayoff(true);
    setTimeout(() => {
      builderRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  }

  // Hint ticker handling
  const [hintTicker, setHintTicker] = useState(null);
  const effectivePre = preloadTicker || hintTicker;

  function handleHint(symbol) {
    handleQuoteLoaded(null);
    setHintTicker(symbol);
  }

  if (!quote) {
    return (
      <div className="analysis-page">
        <div className="search-landing">
          <AnalysisContextCards />
          <TickerSearch
            key={effectivePre || 'default'}
            preloadTicker={effectivePre}
            onQuoteLoaded={handleQuoteLoaded}
          />
          <div className="search-landing-hints">
            {['AAPL', 'SPY', 'TSLA', 'NVDA', 'QQQ', 'AMZN'].map((s) => (
              <button key={s} onClick={() => handleHint(s)}>{s}</button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="analysis-page">
      <div className="search-compact">
        <TickerSearch preloadTicker={null} onQuoteLoaded={handleQuoteLoaded} />
      </div>
      <StockInfoBar quote={quote} />
      <OptionsAnalytics symbol={quote.symbol} />
      <StockChart symbol={quote.symbol} />
      <OptionsChain
        symbol={quote.symbol}
        currentPrice={quote.price}
        onAddLeg={handleAddLeg}
      />
      <div ref={builderRef}>
        <StrategyBuilder
          legs={legs}
          onLegsChange={handleLegsChange}
          currentPrice={quote.price}
          chain={chainData}
          expiration={chainExpiry}
          onAnalyze={handleAnalyze}
          onSaveToSlot={handleSaveToSlot}
          symbol={quote.symbol}
        />
      </div>
      {showPayoff && legs.length > 0 && (
        <PayoffDiagram legs={legs} currentPrice={quote.price} quote={quote} />
      )}
      <StrategyRecommender
        quote={quote}
        onLoadStrategy={handleLoadRecommendation}
      />
      {slotA && slotB && (
        <StrategyComparison
          slotA={slotA}
          slotB={slotB}
          currentPrice={quote.price}
          quote={quote}
          onClear={handleClearComparison}
        />
      )}
    </div>
  );
}
