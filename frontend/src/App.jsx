import { useState } from 'react';
import './App.css';
import DashboardTab from './components/DashboardTab';
import PortfolioTab from './components/PortfolioTab';
import Analysis from './components/Analysis';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [preloadTicker, setPreloadTicker] = useState(null);

  function handleNavigateToAnalysis(ticker) {
    setPreloadTicker(ticker);
    setActiveTab('analysis');
  }

  return (
    <>
      <nav className="tab-bar">
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
            className={`tab-btn ${activeTab === 'analysis' ? 'active' : ''}`}
            onClick={() => setActiveTab('analysis')}
          >
            Analysis
          </button>
        </div>
      </nav>

      {activeTab === 'dashboard' && (
        <DashboardTab onNavigateToAnalysis={handleNavigateToAnalysis} />
      )}
      {activeTab === 'portfolio' && (
        <PortfolioTab onNavigateToAnalysis={handleNavigateToAnalysis} />
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
