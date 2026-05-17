import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { useSourceHealth } from '../hooks/useSourceHealth.js';
import { useSummary } from '../hooks/useSummary.js';
import {
  BarChart, Breakdown, DetectionCards, ErrorBanner, HealthCard,
  Loading, RunCard, fmt, fmtDate
} from './_shared.jsx';

export default function OverviewPage() {
  const { refreshKey } = useOutletContext();
  const summary = useSummary(refreshKey);
  const health = useSourceHealth(refreshKey);
  const runs = useCollectionRuns({ limit: 5 }, refreshKey);
  const d = summary.data || {};
  const latest = runs.data?.runs?.[0] || {};

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Operational Overview</h1>
          <p className="page-subtitle">Security intelligence summary, source health, and active threats.</p>
        </div>
      </div>

      <ErrorBanner error={summary.error || health.error} />
      {summary.loading && <Loading label="Loading overview data" />}

      {/* HERO OVERVIEW */}
      <div className="hero-metrics">
        <div className="metric-card">
          <div className="metric-header">
            Active Threats
            <div className="metric-icon critical"><i className="ti ti-shield-x" /></div>
          </div>
          <div className="metric-value">{fmt(d.detections_by_status?.new || 0)}</div>
          <div className="metric-footer">Pending triage</div>
        </div>
        <div className="metric-card">
          <div className="metric-header">
            High Severity
            <div className="metric-icon high"><i className="ti ti-alert-triangle" /></div>
          </div>
          <div className="metric-value">{fmt(d.detections_by_severity?.high || 0)}</div>
          <div className="metric-footer">Highest priority alerts</div>
        </div>
        <div className="metric-card">
          <div className="metric-header">
            Total Detections
            <div className="metric-icon info"><i className="ti ti-activity" /></div>
          </div>
          <div className="metric-value">{fmt(d.total_detections || 0)}</div>
          <div className="metric-footer">Lifetime in Elasticsearch</div>
        </div>
        <div className="metric-card">
          <div className="metric-header">
            Indexed Last Run
            <div className="metric-icon success"><i className="ti ti-check" /></div>
          </div>
          <div className="metric-value">{fmt(latest.indexed || 0)}</div>
          <div className="metric-footer">New after deduplication</div>
        </div>
      </div>

      {/* SOURCE HEALTH SECTION */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Source Health</span>
        </div>
        <div className="card-body">
          <div className="health-cards">
            {(health.data?.sources || []).map((s) => <HealthCard key={s.source} source={s} />)}
          </div>
        </div>
      </div>

      {/* LIVE DETECTION STREAM AND ANALYTICS */}
      <div className="grid-3">
        <div className="card" style={{ gridColumn: 'span 2' }}>
          <div className="card-header">
            <span className="card-title">Live Detection Stream</span>
            <span className="card-subtitle">{(d.latest_detections || []).length} latest items</span>
          </div>
          <div className="card-body" style={{ maxHeight: '600px', overflowY: 'auto' }}>
            <DetectionCards detections={d.latest_detections || []} />
          </div>
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="card">
            <div className="card-header"><span className="card-title">Severity Breakdown</span></div>
            <div className="card-body"><BarChart data={d.detections_by_severity} /></div>
          </div>
          <div className="card">
            <div className="card-header"><span className="card-title">Category Distribution</span></div>
            <div className="card-body"><Breakdown items={d.detections_by_category || d.detections_by_risk_category} /></div>
          </div>
        </div>
      </div>

    </div>
  );
}
