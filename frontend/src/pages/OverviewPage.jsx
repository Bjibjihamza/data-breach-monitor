import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { useSourceHealth } from '../hooks/useSourceHealth.js';
import { useSummary } from '../hooks/useSummary.js';
import {
  BarChart, Breakdown, DetectionCards, ErrorBanner, HealthCard,
  Loading, fmt
} from './_shared.jsx';

export default function OverviewPage() {
  const { refreshKey } = useOutletContext();
  const summary = useSummary(refreshKey);
  const health = useSourceHealth(refreshKey);
  const runs = useCollectionRuns({ limit: 5 }, refreshKey);

  const d = summary.data || {};
  const latest = runs.data?.runs?.[0] || {};

  // Custom metrics extraction
  const newThreats = d.detections_by_status?.new || 0;
  const highSeverity = d.detections_by_severity?.high || 0;
  const totalDetections = d.total_detections || 0;
  const indexedLatest = latest.indexed || 0;

  return (
    <div className="ov-page">
      <style>{`
        .ov-page {
          padding: 20px 26px;
          display: flex;
          flex-direction: column;
          gap: 28px;
          animation: fade-in 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes fade-in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        
        /* Premium Hero Dashboard */
        .ov-hero {
          position: relative;
          background: linear-gradient(135deg, rgba(16, 18, 23, 0.95) 0%, rgba(5, 7, 10, 0.98) 100%);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 30px 40px;
          overflow: hidden;
          box-shadow: 0 20px 40px -10px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.06);
          display: flex;
          flex-direction: column;
          gap: 32px;
        }
        .ov-hero::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.6), transparent);
        }
        
        .ov-hero-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          z-index: 1;
        }
        .ov-title {
          font-size: 32px;
          font-weight: 700;
          color: #fff;
          margin-bottom: 8px;
          display: flex;
          align-items: center;
          gap: 12px;
          letter-spacing: -0.5px;
        }
        .ov-title i {
          color: #3b82f6;
          text-shadow: 0 0 20px rgba(59, 130, 246, 0.5);
        }
        .ov-subtitle {
          color: #a3aab8;
          font-size: 15px;
          max-width: 600px;
          line-height: 1.6;
        }
        .ov-pulse {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          font-weight: 600;
          color: #10b981;
          background: rgba(16, 185, 129, 0.1);
          padding: 6px 12px;
          border-radius: 20px;
          border: 1px solid rgba(16, 185, 129, 0.2);
        }
        .ov-pulse-dot {
          width: 6px; height: 6px;
          background: #10b981;
          border-radius: 50%;
          box-shadow: 0 0 10px #10b981;
          animation: pulse 2s infinite;
        }

        /* Top KPI Metrics */
        .ov-kpi-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 20px;
          z-index: 1;
        }
        .ov-kpi-card {
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          padding: 18px;
          backdrop-filter: blur(12px);
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
          position: relative;
          overflow: hidden;
        }
        .ov-kpi-card:hover {
          transform: translateY(-4px);
          background: rgba(255,255,255,0.04);
          box-shadow: 0 12px 24px rgba(0,0,0,0.4);
        }
        .ov-kpi-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        .ov-kpi-label {
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: #a3aab8;
          font-weight: 600;
        }
        .ov-kpi-icon {
          width: 32px; height: 32px;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
        }
        .ov-kpi-value {
          font-size: 36px;
          font-weight: 700;
          color: #fff;
          font-family: var(--font-mono);
          margin-bottom: 4px;
        }
        .ov-kpi-footer {
          font-size: 12px;
          color: #687285;
        }
        
        /* KPI Colors */
        .kpi-critical .ov-kpi-icon { background: rgba(255,94,94,0.15); color: #ff5e5e; }
        .kpi-high .ov-kpi-icon { background: rgba(255,157,66,0.15); color: #ff9d42; }
        .kpi-info .ov-kpi-icon { background: rgba(59,130,246,0.15); color: #3b82f6; }
        .kpi-success .ov-kpi-icon { background: rgba(16,185,129,0.15); color: #10b981; }

        /* Premium Panels */
        .ov-panel {
          background: rgba(16, 18, 23, 0.5);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 24px -8px rgba(0,0,0,0.5);
          overflow: hidden;
        }
        .ov-panel-header {
          padding: 20px 24px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255,255,255,0.01);
        }
        .ov-panel-title {
          font-size: 15px;
          font-weight: 600;
          color: #edf0f5;
          display: flex;
          align-items: center;
          gap: 10px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .ov-panel-title i { color: #687285; font-size: 16px; }
        .ov-panel-body { padding: 24px; }

        /* Layouts */
        .ov-grid-3 {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 24px;
        }
        .ov-health-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 20px;
        }
      `}</style>

      <ErrorBanner error={summary.error || health.error} />
      {summary.loading && <Loading label="Initializing Dashboard" />}

      {/* HERO DASHBOARD SECTION */}
      {!summary.loading && (
        <div className="ov-hero">
          <div className="ov-hero-header">
            <div>
              <h1 className="ov-title">
                <i className="ti ti-layout-dashboard"></i>
                Operational Command Center
              </h1>
              <p className="ov-subtitle">
                Global security intelligence summary, active threat triage, and continuous source health monitoring.
              </p>
            </div>
            <div className="ov-pulse">
              <div className="ov-pulse-dot"></div>
              SYSTEM ONLINE
            </div>
          </div>

          <div className="ov-kpi-grid">
            <div className="ov-kpi-card kpi-critical">
              <div className="ov-kpi-header">
                <span className="ov-kpi-label">Active Threats</span>
                <div className="ov-kpi-icon"><i className="ti ti-shield-x"></i></div>
              </div>
              <div className="ov-kpi-value">{fmt(newThreats)}</div>
              <div className="ov-kpi-footer">Pending triage review</div>
            </div>

            <div className="ov-kpi-card kpi-high">
              <div className="ov-kpi-header">
                <span className="ov-kpi-label">High Severity</span>
                <div className="ov-kpi-icon"><i className="ti ti-alert-triangle"></i></div>
              </div>
              <div className="ov-kpi-value">{fmt(highSeverity)}</div>
              <div className="ov-kpi-footer">Critical alerts</div>
            </div>

            <div className="ov-kpi-card kpi-info">
              <div className="ov-kpi-header">
                <span className="ov-kpi-label">Total Signals</span>
                <div className="ov-kpi-icon"><i className="ti ti-activity"></i></div>
              </div>
              <div className="ov-kpi-value">{fmt(totalDetections)}</div>
              <div className="ov-kpi-footer">Lifetime indexed records</div>
            </div>

            <div className="ov-kpi-card kpi-success">
              <div className="ov-kpi-header">
                <span className="ov-kpi-label">Last Run Delta</span>
                <div className="ov-kpi-icon"><i className="ti ti-database"></i></div>
              </div>
              <div className="ov-kpi-value">+{fmt(indexedLatest)}</div>
              <div className="ov-kpi-footer">New unique elements</div>
            </div>
          </div>
        </div>
      )}

      {/* SOURCE HEALTH SECTION (Requested for screenshot) */}
      <div className="ov-panel">
        <div className="ov-panel-header">
          <div className="ov-panel-title">
            <i className="ti ti-heartbeat"></i> Source Infrastructure Health
          </div>
        </div>
        <div className="ov-panel-body" style={{ background: 'rgba(0,0,0,0.1)' }}>
          <div className="ov-health-grid">
            {(health.data?.sources || []).map((s) => (
              <div key={s.source} style={{ background: 'var(--bg-surface)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-subtle)', boxShadow: '0 4px 12px rgba(0,0,0,0.3)' }}>
                <HealthCard source={s} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* LIVE DETECTION STREAM AND ANALYTICS */}
      <div className="ov-grid-3">
        <div className="ov-panel" style={{ gridColumn: 'span 2' }}>
          <div className="ov-panel-header">
            <div className="ov-panel-title">
              <i className="ti ti-list-details"></i> Live Detection Stream
            </div>
            <span className="badge badge-outline" style={{ background: 'rgba(59,130,246,0.1)', borderColor: 'rgba(59,130,246,0.3)', color: '#60a5fa' }}>Latest {(d.latest_detections || []).length} items</span>
          </div>
          <div className="ov-panel-body" style={{ maxHeight: '600px', overflowY: 'auto', padding: '16px', background: 'rgba(0,0,0,0.15)' }}>
            <DetectionCards detections={d.latest_detections || []} />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="ov-panel">
            <div className="ov-panel-header">
              <div className="ov-panel-title">
                <i className="ti ti-chart-bar"></i> Severity Breakdown
              </div>
            </div>
            <div className="ov-panel-body" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <BarChart data={d.detections_by_severity} />
            </div>
          </div>

          <div className="ov-panel">
            <div className="ov-panel-header">
              <div className="ov-panel-title">
                <i className="ti ti-chart-pie"></i> Threat Categories
              </div>
            </div>
            <div className="ov-panel-body" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <Breakdown items={d.detections_by_category || d.detections_by_risk_category} />
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
