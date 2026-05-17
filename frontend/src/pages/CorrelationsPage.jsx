import { useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { getCorrelations } from '../api/analytics.js';
import { useResource } from '../hooks/useResource.js';
import { ErrorBanner, Loading, SeverityBadge, SourceBadge, fmt } from './_shared.jsx';

export default function CorrelationsPage() {
  const { refreshKey } = useOutletContext();
  const loader = useCallback(() => getCorrelations({ limit: 500 }), [refreshKey]);
  const result = useResource(loader, [refreshKey]);
  const rows = result.data?.correlations || [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Correlations</h1>
          <p className="page-subtitle">Grouped signals that point to the same risk across monitored sources</p>
        </div>
      </div>

      <ErrorBanner error={result.error} />
      {result.loading && <Loading label="Loading correlations" />}

      {!result.loading && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Correlated Risks</span>
            <span className="card-subtitle">{fmt(result.data?.total || 0)} groups</span>
          </div>
          <div className="card-body">
            <div className="table-wrap">
              <table className="ops-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Key</th>
                    <th>Sources</th>
                    <th>Detections</th>
                    <th>Severity</th>
                    <th>Confidence</th>
                    <th>Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.correlation_id}>
                      <td>{row.correlation_type}</td>
                      <td>{row.key}</td>
                      <td>
                        <div className="inline-badges">
                          {(row.involved_sources || []).map((source) => <SourceBadge key={source} value={source} />)}
                        </div>
                      </td>
                      <td>{fmt(row.detection_count)}</td>
                      <td><SeverityBadge value={row.severity} /></td>
                      <td>{row.confidence}</td>
                      <td>{row.explanation}</td>
                    </tr>
                  ))}
                  {!rows.length && (
                    <tr><td colSpan="7" className="empty-cell">No correlations found in the latest detection window.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
