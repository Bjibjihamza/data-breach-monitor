import { useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { getSourceDiagnostics } from '../api/analytics.js';
import { useResource } from '../hooks/useResource.js';
import { ErrorBanner, Loading, SourceBadge, fmt, fmtDate, truncate } from './_shared.jsx';

const COLUMN_SETS = {
  queries: ['query', 'risk_category', 'results_seen', 'events_collected', 'skipped_existing', 'content_fetch_failures', 'errors'],
  feeds: ['feed', 'category', 'country', 'entries_seen', 'known_entries', 'new_entries', 'skipped_existing', 'errors'],
  channels: ['channel', 'channel_name', 'messages_seen', 'new_messages', 'messages_already_known', 'skipped_existing', 'last_seen_message_id', 'errors'],
};

function DiagnosticsTable({ source }) {
  const rows = source.rows || [];
  const columns = COLUMN_SETS[source.row_type] || [];
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title"><SourceBadge value={source.source} /></span>
        <span className="card-subtitle">Last run: {fmtDate(source.latest_run?.ended_at)}</span>
      </div>
      <div className="card-body">
        <div className="run-strip">
          <span>Collected: <strong>{fmt(source.latest_run?.collected)}</strong></span>
          <span>Indexed: <strong>{fmt(source.latest_run?.indexed)}</strong></span>
          <span>Duplicates: <strong>{fmt(source.latest_run?.duplicates_skipped)}</strong></span>
          <span>Errors: <strong>{fmt(source.latest_run?.errors)}</strong></span>
        </div>
        <div className="table-wrap">
          <table className="ops-table">
            <thead>
              <tr>{columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${source.source}-${index}`}>
                  {columns.map((column) => (
                    <td key={column}>{typeof row[column] === 'string' ? truncate(row[column], 80) : fmt(row[column])}</td>
                  ))}
                </tr>
              ))}
              {!rows.length && (
                <tr><td colSpan={columns.length || 1} className="empty-cell">No detailed diagnostics persisted for the latest run yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function SourceDiagnosticsPage() {
  const { refreshKey } = useOutletContext();
  const loader = useCallback(() => getSourceDiagnostics(), [refreshKey]);
  const result = useResource(loader, [refreshKey]);
  const sources = result.data?.sources || [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Source Diagnostics</h1>
          <p className="page-subtitle">Per-query, per-feed, and per-channel collection details from recent runs</p>
        </div>
      </div>

      <ErrorBanner error={result.error} />
      {result.loading && <Loading label="Loading source diagnostics" />}
      {!result.loading && sources.map((source) => <DiagnosticsTable key={source.source} source={source} />)}
    </div>
  );
}
