import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import LiveScanStatusCards from '../components/scan/LiveScanStatusCards.jsx';
import SourceRunButton from '../components/scan/SourceRunButton.jsx';
import { useScanStatusContext } from '../context/ScanStatusContext.jsx';
import { runAllSources } from '../api/scans.js';
import { useLatestScan, useLatestScanDetections } from '../hooks/useLatestScan.js';
import { SEVERITIES, SOURCES } from '../utils/constants.js';
import {
  DetectionDrawer,
  DetectionPager,
  Empty,
  ErrorBanner,
  Loading,
  SeverityBadge,
  SourceBadge,
  StatusBadge,
  fmt,
  fmtDate,
  truncate,
} from './_shared.jsx';

const SOURCE_META = {
  github: { title: 'GitHub Intelligence', icon: 'ti-brand-github', accent: '#60a5fa' },
  google_alerts: { title: 'News Intelligence', icon: 'ti-rss', accent: '#f59e0b' },
  telegram: { title: 'Telegram Intelligence', icon: 'ti-brand-telegram', accent: '#38bdf8' },
};

function runStatusClass(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return 'ok';
  if (value === 'failed' || value === 'error') return 'err';
  if (value === 'partial' || value === 'warning') return 'warn';
  return 'idle';
}

function RunStatusBadge({ value }) {
  return <span className={`ls-badge ${runStatusClass(value)}`}>{value || 'unknown'}</span>;
}

function ModeBadge({ value }) {
  return <span className="ls-badge mode">{value || 'unknown'}</span>;
}

function KpiCard({ label, value, icon, tone = 'default' }) {
  return (
    <div className={`ls-kpi ${tone}`}>
      <div className="ls-kpi-icon"><i className={`ti ${icon}`} /></div>
      <div>
        <div className="ls-kpi-value">{fmt(value)}</div>
        <div className="ls-kpi-label">{label}</div>
      </div>
    </div>
  );
}

function Metric({ label, value, mono = false }) {
  return (
    <div className="ls-metric">
      <span>{label}</span>
      <strong className={mono ? 'mono' : ''}>{value || value === 0 ? value : '-'}</strong>
    </div>
  );
}

function SourceCard({ source, data }) {
  const meta = SOURCE_META[source] || { title: source, icon: 'ti-source-code', accent: '#a3aab8' };
  const notRun = !data;
  const seenLabel = source === 'google_alerts' ? 'Entries seen' : source === 'telegram' ? 'Messages seen' : 'Items seen';
  const newLabel = source === 'google_alerts' ? 'New entries' : source === 'telegram' ? 'New messages' : 'New items';
  const seenValue = data?.items_seen || data?.entries_seen || data?.messages_seen;
  const newValue = data?.new_items || data?.new_entries || data?.new_messages;
  return (
    <div className="ls-source-card" style={{ '--source-accent': meta.accent }}>
      <div className="ls-source-header">
        <div className="ls-source-title">
          <i className={`ti ${meta.icon}`} />
          <span>{meta.title}</span>
        </div>
        {notRun ? <span className="ls-badge idle">not run</span> : <RunStatusBadge value={data.status} />}
      </div>
      {notRun ? (
        <div className="ls-source-empty">This source was not part of the latest persisted scan run.</div>
      ) : (
        <>
          <div className="ls-source-grid">
            <Metric label="Mode" value={data.effective_mode} />
            <Metric label="Limit used" value={fmt(data.limit)} />
            <Metric label={seenLabel} value={fmt(seenValue)} />
            <Metric label={newLabel} value={fmt(newValue)} />
            <Metric label="Indexed detections" value={fmt(data.indexed)} />
            <Metric label="Duplicates skipped" value={fmt(data.duplicates)} />
            <Metric label="High severity" value={fmt(data.high_severity)} />
            <Metric label="Errors" value={fmt(data.errors)} />
            <Metric label="Duration" value={data.duration_seconds != null ? `${Number(data.duration_seconds).toFixed(1)}s` : '-'} />
            {source === 'github' && <Metric label="Files fetched" value={fmt(data.files_fetched)} />}
            {source === 'google_alerts' && <Metric label="Feeds scanned" value={fmt(data.feeds_scanned)} />}
            {source === 'telegram' && <Metric label="Channels watched" value={fmt(data.channels_watched)} />}
            {source === 'telegram' && <Metric label="Channels with new" value={fmt(data.channels_with_new_messages)} />}
          </div>
          <div className="ls-cursor-block">
            {source === 'google_alerts' && (
              <Metric label="Latest published" value={fmtDate(data.latest_published_at)} mono />
            )}
            {source === 'telegram' && (
              <>
                <Metric label="Last message id" value={data.last_message_id || '-'} mono />
                <Metric label="Last message date" value={fmtDate(data.last_message_date)} mono />
              </>
            )}
            {source === 'github' && (
              <>
                <Metric label="Cursor before" value={truncate(data.cursor_before, 54) || '-'} mono />
                <Metric label="Cursor after" value={truncate(data.cursor_after, 54) || '-'} mono />
              </>
            )}
          </div>
          {data.message && <div className="ls-source-message">{data.message}</div>}
        </>
      )}
    </div>
  );
}

function DetectionTable({ data, loading, onSelect }) {
  const rows = data?.detections || data?.items || [];
  if (loading) return <Loading label="Loading latest scan detections" />;
  if (!rows.length) return null;
  return (
    <div className="ls-table-wrap">
      <table className="ls-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Source</th>
            <th>Severity</th>
            <th>Risk</th>
            <th>Title</th>
            <th>Organization</th>
            <th>Status</th>
            <th>Source URL</th>
            <th>Detection hash</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const url = row.source_url || row.message_url;
            return (
              <tr key={row.detection_hash || `${row.source}-${row.processed_at}`} onClick={() => onSelect(row)}>
                <td className="mono">{fmtDate(row.processed_at || row.published_at)}</td>
                <td><SourceBadge value={row.source} /></td>
                <td><SeverityBadge value={row.severity} /></td>
                <td className="mono">{fmt(row.risk_score)}</td>
                <td className="ls-title-cell">{truncate(row.title || row.summary || row.text, 84)}</td>
                <td>{truncate(row.organization || row.matched_organization || '-', 34)}</td>
                <td><StatusBadge value={row.status} /></td>
                <td>
                  {url ? (
                    <a href={url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                      Open <i className="ti ti-external-link" />
                    </a>
                  ) : '-'}
                </td>
                <td className="mono">{truncate(row.detection_hash, 18)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function LatestScanPage() {
  const { refreshKey, refresh, setModalOpen } = useOutletContext();
  const { anyActive, refresh: refreshStatus } = useScanStatusContext();
  const [filters, setFilters] = useState({ limit: 50 });
  const [selected, setSelected] = useState(null);
  const report = useLatestScan(refreshKey);
  const detections = useLatestScanDetections(filters, refreshKey);
  const run = report.data?.run;
  const summary = report.data?.summary || {};
  const sources = report.data?.sources || {};

  useEffect(() => {
    setModalOpen(Boolean(selected));
    return () => setModalOpen(false);
  }, [selected, setModalOpen]);

  const set = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }));
  const hasNoNewData = run && String(run.status).toLowerCase() === 'success' && Number(summary.total_new_items || 0) === 0;
  const tableTotal = detections.data?.total ?? 0;

  return (
    <div className="ls-page">
      <style>{`
        .ls-page {
          padding: 28px 32px;
          display: flex;
          flex-direction: column;
          gap: 28px;
          animation: ls-fade-in 0.45s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes ls-fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .ls-hero {
          position: relative;
          overflow: hidden;
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 32px 40px;
          background: linear-gradient(135deg, rgba(14, 18, 26, 0.92), rgba(5, 7, 10, 0.98));
          box-shadow: 0 20px 40px -12px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255,255,255,0.05);
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 24px;
        }
        .ls-hero::before {
          content: '';
          position: absolute;
          inset: 0 0 auto 0;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(20, 184, 166, 0.7), transparent);
        }
        .ls-title {
          font-size: 32px;
          font-weight: 750;
          color: #fff;
          display: flex;
          align-items: center;
          gap: 14px;
          margin: 0 0 10px;
        }
        .ls-title i { color: #2dd4bf; text-shadow: 0 0 20px rgba(45, 212, 191, 0.45); }
        .ls-subtitle {
          color: #a3aab8;
          font-size: 15px;
          line-height: 1.6;
          margin: 0;
          max-width: 680px;
        }
        .ls-run-panel {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
          justify-content: flex-end;
        }
        .ls-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          min-height: 26px;
          padding: 0 10px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.4px;
          text-transform: uppercase;
          border: 1px solid rgba(255,255,255,0.12);
          color: #cbd5e1;
          background: rgba(255,255,255,0.04);
        }
        .ls-badge.ok { color: #34d399; border-color: rgba(52, 211, 153, 0.35); background: rgba(52, 211, 153, 0.09); }
        .ls-badge.warn { color: #fbbf24; border-color: rgba(251, 191, 36, 0.35); background: rgba(251, 191, 36, 0.09); }
        .ls-badge.err { color: #fb7185; border-color: rgba(251, 113, 133, 0.35); background: rgba(251, 113, 133, 0.09); }
        .ls-badge.idle { color: #94a3b8; border-color: rgba(148, 163, 184, 0.24); background: rgba(148, 163, 184, 0.06); }
        .ls-badge.mode { color: #67e8f9; border-color: rgba(103, 232, 249, 0.28); background: rgba(103, 232, 249, 0.08); }
        .ls-run-meta {
          display: grid;
          gap: 6px;
          min-width: 270px;
          color: #94a3b8;
          font-size: 12px;
          font-family: var(--font-mono);
          text-align: right;
        }
        .ls-kpis {
          display: grid;
          grid-template-columns: repeat(6, minmax(0, 1fr));
          gap: 16px;
        }
        .ls-kpi {
          display: flex;
          align-items: center;
          gap: 14px;
          min-height: 96px;
          padding: 18px;
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          background: rgba(16, 18, 23, 0.58);
          box-shadow: 0 8px 24px -12px rgba(0,0,0,0.7);
        }
        .ls-kpi-icon {
          width: 38px;
          height: 38px;
          display: grid;
          place-items: center;
          border-radius: 10px;
          color: #2dd4bf;
          background: rgba(45, 212, 191, 0.09);
          border: 1px solid rgba(45, 212, 191, 0.16);
        }
        .ls-kpi.warn .ls-kpi-icon { color: #fbbf24; background: rgba(251, 191, 36, 0.08); border-color: rgba(251, 191, 36, 0.18); }
        .ls-kpi.err .ls-kpi-icon { color: #fb7185; background: rgba(251, 113, 133, 0.08); border-color: rgba(251, 113, 133, 0.18); }
        .ls-kpi-value { color: #fff; font-size: 25px; font-weight: 760; font-family: var(--font-mono); }
        .ls-kpi-label { margin-top: 4px; color: #687285; font-size: 11px; font-weight: 700; letter-spacing: 0.65px; text-transform: uppercase; }
        .ls-source-grid-wrap {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 18px;
        }
        .ls-source-card {
          border: 1px solid rgba(255,255,255,0.06);
          border-top-color: color-mix(in srgb, var(--source-accent), transparent 50%);
          border-radius: 12px;
          background: rgba(16, 18, 23, 0.55);
          box-shadow: 0 8px 24px -12px rgba(0,0,0,0.7);
          overflow: hidden;
        }
        .ls-source-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 16px 18px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          background: rgba(255,255,255,0.015);
        }
        .ls-source-title {
          display: flex;
          align-items: center;
          gap: 10px;
          color: #edf0f5;
          font-size: 14px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.45px;
        }
        .ls-source-title i { color: var(--source-accent); font-size: 17px; }
        .ls-source-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 1px;
          background: rgba(255,255,255,0.04);
        }
        .ls-metric {
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding: 13px 15px;
          background: rgba(9, 12, 17, 0.78);
        }
        .ls-metric span {
          color: #687285;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.55px;
          text-transform: uppercase;
        }
        .ls-metric strong {
          color: #edf0f5;
          font-size: 13px;
          overflow-wrap: anywhere;
        }
        .mono { font-family: var(--font-mono); }
        .ls-cursor-block {
          display: grid;
          gap: 1px;
          background: rgba(255,255,255,0.04);
          border-top: 1px solid rgba(255,255,255,0.05);
        }
        .ls-source-message, .ls-source-empty {
          padding: 14px 16px;
          color: #a3aab8;
          font-size: 12px;
          line-height: 1.55;
        }
        .ls-panel {
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          background: rgba(16, 18, 23, 0.55);
          box-shadow: 0 8px 24px -12px rgba(0,0,0,0.7);
          overflow: hidden;
        }
        .ls-panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 16px 20px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .ls-panel-title {
          display: flex;
          align-items: center;
          gap: 10px;
          color: #edf0f5;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.45px;
        }
        .ls-filters {
          display: flex;
          align-items: center;
          gap: 12px;
          flex-wrap: wrap;
        }
        .ls-table-wrap { overflow-x: auto; }
        .ls-table {
          width: 100%;
          border-collapse: collapse;
          min-width: 1080px;
        }
        .ls-table th {
          padding: 12px 14px;
          color: #687285;
          font-size: 10px;
          font-weight: 800;
          text-align: left;
          letter-spacing: 0.55px;
          text-transform: uppercase;
          border-bottom: 1px solid rgba(255,255,255,0.06);
          background: rgba(0,0,0,0.24);
        }
        .ls-table td {
          padding: 13px 14px;
          color: #d7dde8;
          font-size: 12px;
          border-bottom: 1px solid rgba(255,255,255,0.045);
          vertical-align: middle;
        }
        .ls-table tbody tr {
          cursor: pointer;
          transition: background 0.15s ease;
        }
        .ls-table tbody tr:hover { background: rgba(45, 212, 191, 0.06); }
        .ls-table a {
          color: #67e8f9;
          display: inline-flex;
          align-items: center;
          gap: 4px;
          text-decoration: none;
        }
        .ls-title-cell {
          color: #f8fafc;
          font-weight: 600;
          max-width: 340px;
        }
        .ls-empty-wrap { padding: 24px; }
        @media (max-width: 1200px) {
          .ls-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); }
          .ls-source-grid-wrap { grid-template-columns: 1fr; }
          .ls-hero { align-items: flex-start; flex-direction: column; }
          .ls-run-panel { justify-content: flex-start; }
          .ls-run-meta { text-align: left; }
        }
        @media (max-width: 720px) {
          .ls-page { padding: 20px 16px; }
          .ls-hero { padding: 24px; }
          .ls-title { font-size: 25px; }
          .ls-kpis { grid-template-columns: 1fr; }
          .ls-panel-header { align-items: flex-start; flex-direction: column; }
        }
      `}</style>

      <ErrorBanner error={report.error || detections.error} />

      <LiveScanStatusCards title="Live Scan Status" compact />
      <div className="scan-actions" style={{ marginBottom: 8 }}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={anyActive}
          onClick={async () => {
            await runAllSources('incremental');
            await refreshStatus();
            refresh?.();
          }}
        >
          <i className="ti ti-radar-2" /> Run All Sources
        </button>
        <SourceRunButton source="github" onStarted={() => refresh?.()} />
        <SourceRunButton source="google_alerts" onStarted={() => refresh?.()} />
        <SourceRunButton source="telegram" onStarted={() => refresh?.()} />
      </div>

      <div className="ls-hero">
        <div>
          <h1 className="ls-title">
            <i className="ti ti-radar-2" />
            Last Scan Intelligence
          </h1>
          <p className="ls-subtitle">
            Focused view of the most recent GitHub, Google Alerts, and Telegram collection run.
          </p>
        </div>
        <div className="ls-run-panel">
          {run && <RunStatusBadge value={run.status} />}
          {run && <ModeBadge value={run.effective_mode} />}
          <button className="btn btn-outline" onClick={refresh}>
            <i className="ti ti-refresh" />
            Refresh
          </button>
          {run && (
            <div className="ls-run-meta">
              <span>Started {fmtDate(run.started_at)}</span>
              <span>Finished {fmtDate(run.finished_at)}</span>
              <span>Duration {run.duration_seconds != null ? `${Number(run.duration_seconds).toFixed(1)}s` : '-'}</span>
            </div>
          )}
        </div>
      </div>

      {report.loading && <Loading label="Loading latest scan report" />}

      {!report.loading && !run && (
        <Empty title="No scan run found yet" sub="Launch a scan to generate the latest scan report." />
      )}

      {!report.loading && run && (
        <>
          <div className="ls-kpis">
            <KpiCard label="Total items seen" value={summary.total_items_seen} icon="ti-eye-search" />
            <KpiCard label="New unique elements" value={summary.total_new_items} icon="ti-sparkles" />
            <KpiCard label="Indexed detections" value={summary.total_indexed} icon="ti-database-plus" />
            <KpiCard label="Duplicates skipped" value={summary.total_duplicates} icon="ti-copy-off" tone="warn" />
            <KpiCard label="High severity" value={summary.high_severity} icon="ti-alert-triangle" tone="warn" />
            <KpiCard label="Errors" value={summary.total_errors} icon="ti-alert-circle" tone={Number(summary.total_errors || 0) ? 'err' : 'default'} />
          </div>

          <div className="ls-source-grid-wrap">
            {SOURCES.map((item) => (
              <SourceCard key={item.value} source={item.value} data={sources[item.value]} />
            ))}
          </div>

          <div className="ls-panel">
            <div className="ls-panel-header">
              <div>
                <div className="ls-panel-title">
                  <i className="ti ti-list-search" />
                  Detections from latest scan
                </div>
                <div style={{ color: '#687285', fontSize: '12px', marginTop: '6px' }}>
                  {fmt(tableTotal)} detections indexed during this run
                </div>
              </div>
              <div className="ls-filters">
                <select className="filter-select" value={filters.source || ''} onChange={set('source')}>
                  <option value="">Any source</option>
                  {SOURCES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <select className="filter-select" value={filters.severity || ''} onChange={set('severity')}>
                  <option value="">Any severity</option>
                  {SEVERITIES.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </div>
            </div>
            <DetectionTable data={detections.data} loading={detections.loading} onSelect={setSelected} />
            {!detections.loading && tableTotal === 0 && (
              <div className="ls-empty-wrap">
                <Empty
                  title={hasNoNewData ? 'Latest scan completed successfully' : 'No detections from this run'}
                  sub={hasNoNewData ? 'No new elements were discovered.' : 'This run did not index detections matching the current filters.'}
                />
              </div>
            )}
            <div style={{ padding: '0 20px 20px' }}>
              <DetectionPager
                data={detections.data}
                loadingMore={detections.loadingMore}
                onLoadMore={detections.loadMore}
              />
            </div>
          </div>
        </>
      )}

      <DetectionDrawer detection={selected} onClose={() => setSelected(null)} onUpdated={setSelected} />
    </div>
  );
}
