import { useState, useEffect } from 'react';
import './App.css';
import DashboardTab from './components/DashboardTab';
import PortfolioTab from './components/PortfolioTab';
import Valuations from './components/Valuations';
import Analysis from './components/Analysis';

function useMarketOpen() {
  const [isOpen, setIsOpen] = useState(false);
  useEffect(() => {
    function check() {
      const now = new Date();
      const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      const day = et.getDay();
      const h = et.getHours();
      const m = et.getMinutes();
      const mins = h * 60 + m;
      // Mon-Fri, 9:30 AM - 4:00 PM ET
      setIsOpen(day >= 1 && day <= 5 && mins >= 570 && mins < 960);
    }
    check();
    const id = setInterval(check, 30000); // re-check every 30s
    return () => clearInterval(id);
  }, []);
  return isOpen;
}

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [preloadTicker, setPreloadTicker] = useState(null);
  const marketOpen = useMarketOpen();

  function handleNavigateToAnalysis(ticker) {
    setPreloadTicker(ticker);
    setActiveTab('analysis');
  }

  return (
    <>
      <nav className="tab-bar">
        <div className="tab-bar-container">
          <div className="tab-bar-inner">
            <button
              className={`tab-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => setActiveTab('dashboard')}
            >
              Dashboard
            </button>
            <button
              className={`tab-btn ${activeTab === 'portfolio' ? 'active' : ''}`}
              onClick={() => setActiveTab('portfolio')}
            >
              Portfolio
            </button>
            <button
              className={`tab-btn ${activeTab === 'valuations' ? 'active' : ''}`}
              onClick={() => setActiveTab('valuations')}
            >
              Valuations
            </button>
            <button
              className={`tab-btn ${activeTab === 'analysis' ? 'active' : ''}`}
              onClick={() => setActiveTab('analysis')}
            >
              Analysis
            </button>
          </div>
          <div className="market-status">
            <span className={`market-dot ${marketOpen ? 'open' : 'closed'}`} />
            <span className="market-label">{marketOpen ? 'Market Open' : 'Market Closed'}</span>
          </div>
        </div>
      </nav>

      {activeTab === 'dashboard' && (
        <DashboardTab onNavigateToAnalysis={handleNavigateToAnalysis} />
      )}
      {activeTab === 'portfolio' && (
        <PortfolioTab onNavigateToAnalysis={handleNavigateToAnalysis} />
      )}
      {activeTab === 'valuations' && (
        <Valuations />
      )}
      {activeTab === 'analysis' && (
        <Analysis
          preloadTicker={preloadTicker}
          onTickerLoaded={() => setPreloadTicker(null)}
        />
      )}
    </>
  );
}

export default App;
