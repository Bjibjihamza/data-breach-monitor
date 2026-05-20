import { fmt, fmtDate } from '../../pages/_shared.jsx';
import { useScanStatusContext } from '../../context/ScanStatusContext.jsx';
import { ScanStyles } from './ScanStyles.jsx';
import { SOURCE_META, isActiveStatus, progressPercent, shortenId, statusTone } from './scanUi.js';

function StatusBadge({ status }) {
  const tone = statusTone(status);
  const label = String(status || 'idle').replace(/_/g, ' ');
  return (
    <span className={`scan-badge ${tone}`}>
      {isActiveStatus(status) && <i className="ti ti-loader-2 scan-spinner" />}
      {label}
    </span>
  );
}

function sourceExtras(sourceKey, source) {
  const p = source.progress || {};
  if (sourceKey === 'github') {
    return [
      ['Queries', `${fmt(p.queries_processed ?? p.processed_items)} / ${fmt(p.queries_total ?? p.configured_items)}`],
      ['Files fetched', fmt(p.files_fetched)],
      ['Validated', fmt(p.validated_candidates)],
      ['Rejected placeholders', fmt(p.rejected_placeholders)],
    ];
  }
  if (sourceKey === 'google_alerts') {
    return [
      ['Feeds', `${fmt(p.feeds_processed ?? p.processed_items)} / ${fmt(p.feeds_total ?? p.configured_items)}`],
      ['Entries seen', fmt(p.entries_seen ?? p.items_seen)],
      ['Entries indexed', fmt(p.entries_indexed ?? p.items_indexed)],
      ['Latest published', fmtDate(p.latest_published_at || source.latest_published_at)],
    ];
  }
  if (sourceKey === 'telegram') {
    return [
      ['Channels', `${fmt(p.channels_processed ?? p.processed_items)} / ${fmt(p.channels_total ?? p.configured_items)}`],
      ['Messages seen', fmt(p.messages_seen ?? p.items_seen)],
      ['Messages indexed', fmt(p.messages_indexed ?? p.items_indexed)],
      ['Last message id', p.last_message_id ?? '—'],
    ];
  }
  return [];
}

function ScanCard({ sourceKey }) {
  const meta = SOURCE_META[sourceKey];
  const { sourceStatus } = useScanStatusContext();
  const source = sourceStatus(sourceKey);
  const running = isActiveStatus(source.status);
  const pct = progressPercent(source);
  const extras = sourceExtras(sourceKey, source);

  return (
    <div className={`scan-card${running ? ' running' : ''}`}>
      <div className="scan-card-header">
        <div className="scan-card-title">
          <i className={`ti ${meta.icon}`} style={{ color: meta.accent }} />
          <span>{meta.title}</span>
        </div>
        <StatusBadge status={source.status} />
      </div>
      <div className="scan-metrics">
        <div className="scan-metric"><span>Phase</span><strong>{source.phase || '—'}</strong></div>
        <div className="scan-metric"><span>Mode</span><strong>{source.effective_mode || source.requested_mode || '—'}</strong></div>
        <div className="scan-metric"><span>Duration</span><strong>{source.duration_seconds != null ? `${Number(source.duration_seconds).toFixed(0)}s` : '—'}</strong></div>
        <div className="scan-metric"><span>Items seen</span><strong>{fmt(source.items_seen ?? source.progress?.items_seen)}</strong></div>
        <div className="scan-metric"><span>Indexed</span><strong>{fmt(source.items_indexed ?? source.progress?.items_indexed)}</strong></div>
        <div className="scan-metric"><span>Skipped</span><strong>{fmt(source.duplicates_skipped ?? source.progress?.duplicates_skipped)}</strong></div>
        <div className="scan-metric"><span>Errors</span><strong>{fmt(source.errors ?? source.progress?.errors)}</strong></div>
        {extras.map(([label, value]) => (
          <div key={label} className="scan-metric"><span>{label}</span><strong>{value}</strong></div>
        ))}
      </div>
      {pct != null && (
        <div className="scan-progress" title={`${pct}%`}>
          <div style={{ width: `${pct}%` }} />
        </div>
      )}
      {source.message && <div className="scan-message">{source.message}</div>}
      {source.last_error && (
        <div className="scan-message" style={{ color: '#fb7185' }}>{source.last_error}</div>
      )}
      <div className="scan-meta">
        <span>Updated {fmtDate(source.updated_at)}</span>
        <span>Task {shortenId(source.task_id, 12)}</span>
        <span>Run {shortenId(source.run_id, 12)}</span>
        <span>Group {shortenId(source.scan_group_id, 12)}</span>
      </div>
    </div>
  );
}

export default function LiveScanStatusCards({ title = 'Live Scan Status', compact = false }) {
  const { loading, error, anyRunning, scanGroupId } = useScanStatusContext();

  return (
    <section>
      <ScanStyles />
      {!compact && (
        <div className="scan-panel-header" style={{ marginBottom: 16 }}>
          <div>
            <h2 className="scan-panel-title"><i className="ti ti-activity" /> {title}</h2>
            {anyRunning && (
              <div className="scan-message">
                Scan in progress{scanGroupId ? ` · group ${shortenId(scanGroupId, 16)}` : ''}
              </div>
            )}
            {loading && !error && <div className="scan-message">Loading live status…</div>}
            {error && <div className="scan-message" style={{ color: '#fb7185' }}>{error.message}</div>}
          </div>
        </div>
      )}
      <div className="scan-grid">
        {Object.keys(SOURCE_META).map((key) => (
          <ScanCard key={key} sourceKey={key} />
        ))}
      </div>
    </section>
  );
}
