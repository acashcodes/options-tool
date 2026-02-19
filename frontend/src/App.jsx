import { useState } from 'react';
import './App.css';
import Dashboard from './components/Dashboard';
import Analysis from './components/Analysis';

function App() {
  const [activeTab, setActiveTab] = useState('analysis');
  const [preloadTicker, setPreloadTicker] = useState(null);

  function handleNavigateToAnalysis(ticker) {
    setPreloadTicker(ticker);
    setActiveTab('analysis');
  }

  return (
    <>
      <nav className="tab-bar">
        <span className="app-title">OPTIONS ANALYZER</span>
        <button
          className={activeTab === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={activeTab === 'analysis' ? 'active' : ''}
          onClick={() => setActiveTab('analysis')}
        >
          Analysis
        </button>
      </nav>

      {activeTab === 'dashboard' && (
        <Dashboard onNavigateToAnalysis={handleNavigateToAnalysis} />
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
