import { useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { getIntelligenceSummary } from '../api/analytics.js';
import { useResource } from '../hooks/useResource.js';
import { DetectionCards, ErrorBanner, Loading, SourceBadge, fmt } from './_shared.jsx';

function CountList({ items, labelKey }) {
  if (!items?.length) return <div className="empty-cell">No data.</div>;
  return (
    <div className="count-list">
      {items.map((item) => (
        <div key={item[labelKey] || item.source || item.keyword || item.cve_id} className="count-row">
          <span>{item[labelKey] || item.source || item.keyword || item.cve_id}</span>
          <strong>{fmt(item.count)}</strong>
        </div>
      ))}
    </div>
  );
}

export default function IntelligencePage() {
  const { refreshKey } = useOutletContext();
  const loader = useCallback(() => getIntelligenceSummary({ limit: 500 }), [refreshKey]);
  const result = useResource(loader, [refreshKey]);
  const d = result.data || {};

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Intelligence Summary</h1>
          <p className="page-subtitle">Deterministic summary of current high-risk signals and analyst priorities</p>
        </div>
      </div>

      <ErrorBanner error={result.error} />
      {result.loading && <Loading label="Building intelligence summary" />}

      {!result.loading && (
        <>
          <div className="hero-metrics">
            <div className="metric-card">
              <div className="metric-header">Input Window <div className="metric-icon info"><i className="ti ti-database" /></div></div>
              <div className="metric-value">{fmt(d.generated_from_detections || 0)}</div>
              <div className="metric-footer">Recent detections analyzed</div>
            </div>
            <div className="metric-card">
              <div className="metric-header">High Risk <div className="metric-icon high"><i className="ti ti-alert-triangle" /></div></div>
              <div className="metric-value">{fmt(d.latest_high_risk_findings?.length || 0)}</div>
              <div className="metric-footer">Latest high-severity findings</div>
            </div>
            <div className="metric-card">
              <div className="metric-header">Confirmed Signals <div className="metric-icon critical"><i className="ti ti-shield-check" /></div></div>
              <div className="metric-value">{fmt(d.confirmed_exposure_signals?.length || 0)}</div>
              <div className="metric-footer">Confirmed or escalation-ready items</div>
            </div>
          </div>

          <div className="grid-3">
            <div className="card">
              <div className="card-header"><span className="card-title">Affected Entities</span></div>
              <div className="card-body"><CountList items={d.affected_organizations} labelKey="organization" /></div>
            </div>
            <div className="card">
              <div className="card-header"><span className="card-title">Risk Sources</span></div>
              <div className="card-body">
                <div className="count-list">
                  {(d.top_risk_sources || []).map((item) => (
                    <div key={item.source} className="count-row">
                      <SourceBadge value={item.source} />
                      <strong>{fmt(item.count)}</strong>
                    </div>
                  ))}
                  {!d.top_risk_sources?.length && <div className="empty-cell">No data.</div>}
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-header"><span className="card-title">Recommended Actions</span></div>
              <div className="card-body">
                <ul className="action-list">
                  {(d.recommended_actions || []).map((action) => <li key={action}>{action}</li>)}
                </ul>
              </div>
            </div>
          </div>

          <div className="grid-2">
            <div className="card">
              <div className="card-header"><span className="card-title">Repeated CVEs</span></div>
              <div className="card-body"><CountList items={d.repeated_cves} labelKey="cve_id" /></div>
            </div>
            <div className="card">
              <div className="card-header"><span className="card-title">Repeated Keywords</span></div>
              <div className="card-body"><CountList items={d.repeated_keywords} labelKey="keyword" /></div>
            </div>
          </div>

          <div className="card">
            <div className="card-header"><span className="card-title">Latest High-Risk Findings</span></div>
            <div className="card-body"><DetectionCards detections={d.latest_high_risk_findings || []} /></div>
          </div>
        </>
      )}
    </div>
  );
}
