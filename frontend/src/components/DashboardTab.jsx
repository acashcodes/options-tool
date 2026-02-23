import MarketOverviewBar from './MarketOverviewBar';
import AlertsPanel from './AlertsPanel';

export default function DashboardTab({ onNavigateToAnalysis }) {
  return (
    <div className="dashboard-tab">
      <MarketOverviewBar />
      <AlertsPanel onNavigateToAnalysis={onNavigateToAnalysis} />
    </div>
  );
}
