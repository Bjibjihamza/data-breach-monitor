import { fmt, fmtDate } from '../../pages/_shared.jsx';
import { useScanStatusContext } from '../../context/ScanStatusContext.jsx';
import SourceRunButton from './SourceRunButton.jsx';
import { ScanStyles } from './ScanStyles.jsx';
import { SOURCE_META, isActiveStatus, progressPercent, shortenId, statusTone } from './scanUi.js';

function githubExtras(source) {
  const p = source.progress || {};
  return [
    ['Queries processed', fmt(p.queries_processed ?? p.processed_items)],
    ['Files fetched', fmt(p.files_fetched)],
    ['Skipped low confidence', fmt(p.skipped_low_confidence)],
    ['Validated candidates', fmt(p.validated_candidates)],
    ['Rejected placeholders', fmt(p.rejected_placeholders)],
    ['Rate limit remaining', p.rate_limit_remaining ?? '—'],
  ];
}

function newsExtras(source) {
  const p = source.progress || {};
  return [
    ['Feeds processed', fmt(p.feeds_processed ?? p.processed_items)],
    ['Entries collected', fmt(p.items_collected)],
    ['Latest published', fmtDate(p.latest_published_at || source.latest_published_at)],
  ];
}

function telegramExtras(source) {
  const p = source.progress || {};
  return [
    ['Channels processed', fmt(p.channels_processed ?? p.processed_items)],
    ['Messages collected', fmt(p.items_collected)],
    ['Last message id', p.last_message_id ?? '—'],
    ['Last message date', fmtDate(p.last_message_date || source.last_message_date)],
  ];
}

const EXTRAS = {
  github: githubExtras,
  google_alerts: newsExtras,
  telegram: telegramExtras,
};

export default function SourceRunPanel({ source, onScanStarted }) {
  const meta = SOURCE_META[source];
  const { sourceStatus } = useScanStatusContext();
  const data = sourceStatus(source);
  const tone = statusTone(data.status);
  const pct = progressPercent(data);
  const extras = (EXTRAS[source] || (() => []))(data);

  let emptyMessage = 'No scan has run yet.';
  if (isActiveStatus(data.status)) {
    emptyMessage = 'Scan is currently running. Results will update automatically.';
  } else if (data.status === 'success' && Number(data.items_indexed ?? data.progress?.items_indexed ?? 0) === 0) {
    emptyMessage = 'Scan completed successfully. No new elements were discovered.';
  } else if (data.status === 'failed') {
    emptyMessage = data.last_error || data.message || 'Scan failed.';
  }

  return (
    <div className="scan-panel">
      <ScanStyles />
      <div className="scan-panel-header">
        <div className="scan-panel-title">
          <i className={`ti ${meta.icon}`} style={{ color: meta.accent }} />
          Current Run Status
        </div>
        <div className="scan-actions">
          <SourceRunButton source={source} onStarted={onScanStarted} />
        </div>
      </div>
      <span className={`scan-badge ${tone}`}>{data.status || 'idle'}</span>
      {data.status === 'idle' && !data.run_id ? (
        <div className="scan-message" style={{ marginTop: 12 }}>{emptyMessage}</div>
      ) : (
        <>
          <div className="scan-metrics" style={{ marginTop: 14 }}>
            <div className="scan-metric"><span>Phase</span><strong>{data.phase || '—'}</strong></div>
            <div className="scan-metric"><span>Mode</span><strong>{data.effective_mode || '—'}</strong></div>
            <div className="scan-metric"><span>Duration</span><strong>{data.duration_seconds != null ? `${Number(data.duration_seconds).toFixed(0)}s` : '—'}</strong></div>
            <div className="scan-metric"><span>Indexed</span><strong>{fmt(data.items_indexed ?? data.progress?.items_indexed)}</strong></div>
            <div className="scan-metric"><span>Errors</span><strong>{fmt(data.errors ?? data.progress?.errors)}</strong></div>
            {extras.map(([label, value]) => (
              <div key={label} className="scan-metric"><span>{label}</span><strong>{value}</strong></div>
            ))}
          </div>
          {pct != null && (
            <div className="scan-progress" style={{ marginTop: 12 }}>
              <div style={{ width: `${pct}%` }} />
            </div>
          )}
          {data.message && <div className="scan-message">{data.message}</div>}
          {(data.status === 'failed' || data.last_error) && (
            <div className="scan-message" style={{ color: '#fb7185' }}>
              {data.last_error || emptyMessage}
              {data.task_id && <> Â· Task {shortenId(data.task_id, 14)}</>}
              {data.updated_at && <> Â· {fmtDate(data.updated_at)}</>}
            </div>
          )}
          <div className="scan-meta">
            <span>Run {shortenId(data.run_id, 16)}</span>
            <span>Task {shortenId(data.task_id, 16)}</span>
          </div>
        </>
      )}
    </div>
  );
}
