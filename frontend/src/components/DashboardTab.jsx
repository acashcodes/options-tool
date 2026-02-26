import MarketOverviewBar from './MarketOverviewBar';
import AlertsPanel from './AlertsPanel';
import NewsletterPanel from './NewsletterPanel';

export default function DashboardTab({ onNavigateToAnalysis }) {
  return (
    <div className="dashboard-tab">
      <MarketOverviewBar />
      <div className="dashboard-columns">
        <div className="dashboard-col-left">
          <AlertsPanel onNavigateToAnalysis={onNavigateToAnalysis} />
        </div>
        <div className="dashboard-col-right">
          <NewsletterPanel />
        </div>
      </div>
    </div>
  );
}
