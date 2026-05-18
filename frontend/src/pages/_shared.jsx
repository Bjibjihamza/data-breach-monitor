import { useState, useEffect } from 'react';
import { updateDetectionStatus } from '../api/detections.js';
import { STATUSES } from '../utils/constants.js';

export function fmt(n) {
  if (n == null || n === '' || n === undefined) return '—';
  return Number(n).toLocaleString();
}

export function fmtDate(v) {
  if (!v) return '—';
  try { return new Date(v).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return v; }
}

export function truncate(s, n = 80) {
  if (!s) return '';
  return String(s).length > n ? String(s).slice(0, n) + '…' : String(s);
}

export function compactJson(obj) {
  try { return JSON.stringify(obj, null, 2); } catch { return '{}'; }
}

export function SourceBadge({ value }) {
  const map = { github: 'badge-src-github', google_alerts: 'badge-src-google', telegram: 'badge-src-telegram' };
  const labels = { github: 'GitHub', google_alerts: 'Google', telegram: 'Telegram' };
  const icons = { github: 'ti-brand-github', google_alerts: 'ti-rss', telegram: 'ti-brand-telegram' };
  return (
    <span className={`badge ${map[value] || 'badge-outline'}`}>
      <i className={`ti ${icons[value] || 'ti-link'}`} style={{ marginRight: '4px', fontSize: '13px' }} />
      {labels[value] || value || 'unknown'}
    </span>
  );
}

export function SeverityBadge({ value }) {
  const v = String(value || '').toLowerCase();
  const map = { high: 'badge-sev-high', medium: 'badge-sev-medium', low: 'badge-sev-low', informational: 'badge-outline' };
  return <span className={`badge ${map[v] || 'badge-outline'}`}>{value || 'unknown'}</span>;
}

export function StatusBadge({ value }) {
  const v = String(value || '').toLowerCase();
  const map = {
    new: 'badge-stat-new',
    reviewed: 'badge-stat-reviewed',
    confirmed: 'badge-stat-hot',
    escalated: 'badge-stat-hot',
    false_positive: 'badge-stat-muted',
    ignored: 'badge-stat-muted'
  };
  return <span className={`badge ${map[v] || 'badge-outline'}`}>{value || 'unknown'}</span>;
}

export function ErrorBanner({ error }) {
  if (!error) return null;
  return (
    <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--status-critical)', color: 'var(--status-critical)', padding: '12px 16px', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: '8px' }}>
      <i className="ti ti-alert-triangle" style={{ fontSize: '18px' }} />
      <strong>Error:</strong> {error.message || String(error)}
    </div>
  );
}

export function Empty({ title = 'No data', sub = 'Run a collection or adjust filters.' }) {
  return (
    <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-tertiary)', border: '1px dashed var(--border-default)', borderRadius: 'var(--radius-lg)' }}>
      <i className="ti ti-inbox" style={{ fontSize: '32px', marginBottom: '12px', display: 'block' }} />
      <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>{title}</div>
      <div style={{ fontSize: '12px' }}>{sub}</div>
    </div>
  );
}

export function Loading({ label = 'Loading' }) {
  return (
    <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-tertiary)' }}>
      <i className="ti ti-loader-2" style={{ fontSize: '24px', animation: 'spin 1s linear infinite', display: 'inline-block', marginBottom: '8px' }} />
      <div>{label}…</div>
      <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export function JsonBlock({ data }) {
  return <pre className="evidence-box">{compactJson(data)}</pre>;
}

export function BarChart({ data }) {
  const entries = Array.isArray(data)
    ? data
    : Object.entries(data || {}).map(([label, value]) => ({ label, value }));
  if (!entries.length) return <div style={{ color: 'var(--text-tertiary)' }}>No chart data.</div>;
  const max = Math.max(...entries.map((e) => Number(e.value ?? e.count ?? 0)), 1);
  return (
    <div className="chart-container">
      {entries.map((e, i) => {
        const val = Number(e.value ?? e.count ?? 0);
        const h = Math.max(4, (val / max) * 100);
        return (
          <div className="chart-bar-wrapper" key={i} title={`${e.label}: ${val}`}>
            <div className="chart-bar" style={{ height: `${h}%` }} />
            <div className="chart-label">{truncate(String(e.label || ''), 10)}</div>
          </div>
        );
      })}
    </div>
  );
}

export function Breakdown({ items }) {
  const entries = Object.entries(items || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, v]) => Number(v)), 1);
  if (!entries.length) return <div style={{ color: 'var(--text-tertiary)' }}>No data.</div>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {entries.map(([label, value]) => (
        <div key={label} style={{ display: 'grid', gap: '4px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
            <span style={{ color: 'var(--text-secondary)' }}>{label || 'unknown'}</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{fmt(value)}</span>
          </div>
          <div style={{ height: '4px', background: 'var(--bg-active)', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${(Number(value) / max) * 100}%`, background: 'var(--accent-primary)' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function DetectionCards({ detections = [], onSelect }) {
  if (!detections.length) return <Empty title="No detections" />;
  return (
    <div className="detection-list">
      {detections.map((row) => {
        const sevClass = String(row.severity || '').toLowerCase();
        return (
          <div 
            key={row.detection_hash || `${row.source}-${row.title}-${row.processed_at}`} 
            className={`detection-card severity-${sevClass}`}
            onClick={() => onSelect?.(row)}
          >
            <div className="detection-main">
              <div className="detection-meta-top">
                <span>{fmtDate(row.processed_at || row.published_at)}</span>
                <span>•</span>
                <span style={{ color: 'var(--text-primary)' }}>Confidence: {row.confidence || '—'}</span>
                {row.category && (
                  <>
                    <span>•</span>
                    <span>{row.category}</span>
                  </>
                )}
              </div>
              <div className="detection-title">
                {truncate(row.title || row.summary || row.text, 120)}
              </div>
              <div className="detection-meta-bottom">
                <SourceBadge value={row.source} />
                <SeverityBadge value={row.severity} />
                <StatusBadge value={row.status} />
              </div>
            </div>
            <div className="detection-actions">
              <button className="btn btn-outline" style={{ height: '28px', padding: '0 8px', fontSize: '11px' }}>
                <i className="ti ti-eye" /> Review
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function DetectionDrawer({ detection, onClose, onUpdated }) {
  const [tab, setTab] = useState('details');
  const [current, setCurrent] = useState(detection);
  const [reviewStatus, setReviewStatus] = useState(detection?.status || 'new');
  const [reviewNote, setReviewNote] = useState(detection?.review_note || '');
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState('');
  const [reviewSaved, setReviewSaved] = useState(false);

  useEffect(() => {
    setCurrent(detection);
    setReviewStatus(detection?.status || 'new');
    setReviewNote(detection?.review_note || '');
    setReviewError('');
    setReviewSaved(false);
  }, [detection]);
  
  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    if (detection) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [detection, onClose]);

  if (!current) return null;
  const link = current.source_url || current.message_url;

  const saveReview = async () => {
    if (!current?.detection_hash) return;
    setReviewBusy(true);
    setReviewError('');
    setReviewSaved(false);
    try {
      const result = await updateDetectionStatus(current.detection_hash, reviewStatus, reviewNote);
      const updated = {
        ...current,
        status: result.status || reviewStatus,
        triage_status: result.status || reviewStatus,
        review_note: reviewNote,
        reviewed_by: 'dashboard',
        reviewed_at: new Date().toISOString()
      };
      setCurrent(updated);
      onUpdated?.(updated);
      setReviewSaved(true);
    } catch (error) {
      setReviewError(error.message || 'Review update failed');
    } finally {
      setReviewBusy(false);
    }
  };

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div className="drawer-top">
            <h2 className="drawer-title">{current.title || current.summary || 'Detection'}</h2>
            <button className="drawer-close" onClick={onClose}><i className="ti ti-x" style={{ fontSize: '20px' }} /></button>
          </div>
          <div className="drawer-meta">
            <SourceBadge value={current.source} />
            <SeverityBadge value={current.severity} />
            <StatusBadge value={current.status} />
            {link && (
              <a href={link} target="_blank" rel="noreferrer" className="btn btn-outline" style={{ marginLeft: 'auto', height: '24px', fontSize: '11px' }}>
                View Original <i className="ti ti-external-link" />
              </a>
            )}
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '8px', padding: '0 24px', borderBottom: '1px solid var(--border-subtle)' }}>
          {['details', 'evidence', 'review', 'raw'].map((t) => (
            <button 
              key={t} 
              onClick={() => setTab(t)}
              style={{
                padding: '12px 16px',
                fontSize: '13px',
                fontWeight: 500,
                color: tab === t ? 'var(--accent-primary)' : 'var(--text-secondary)',
                borderBottom: `2px solid ${tab === t ? 'var(--accent-primary)' : 'transparent'}`,
                textTransform: 'capitalize'
              }}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="drawer-body">
          {tab === 'details' && (
            <div className="drawer-section">
              <div className="drawer-section-title">Metadata</div>
              <dl className="drawer-grid">
                {[
                  ['Detection ID', current.detection_hash],
                  ['Risk Score', current.risk_score ? <span className="text-high">{current.risk_score}</span> : null],
                  ['Confidence', current.confidence],
                  ['Category', current.category || current.risk_category],
                  ['Signal Type', current.signal_type],
                  ['Affected Entity', current.organization],
                  ['Country', current.country],
                  ['CVE IDs', (current.cve_ids || []).join(', ') || null],
                  ['Keywords', (current.detected_keywords || []).join(', ') || null],
                  ['Processed', fmtDate(current.processed_at)],
                  ['Published', fmtDate(current.published_at)],
                ].filter(([, v]) => v != null && v !== '').map(([k, v]) => (
                  <div key={k} style={{ display: 'contents' }}>
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          {tab === 'evidence' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              {[
                ['Redacted Text', current.redacted_text || current.text || current.summary],
                ['Evidence Excerpt', current.evidence_excerpt],
                ['Evidence Lines', (current.evidence_lines || []).join('\n')],
              ].map(([title, text]) => (
                <div className="drawer-section" key={title}>
                  <div className="drawer-section-title">{title}</div>
                  <div className="evidence-box">{text || `No ${title.toLowerCase()} available.`}</div>
                </div>
              ))}
            </div>
          )}
          {tab === 'review' && (
            <div className="drawer-section">
              <div className="drawer-section-title">Analyst Review</div>
              <div className="review-panel">
                <label className="review-field">
                  <span>Status</span>
                  <select className="filter-select" value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value)} disabled={reviewBusy}>
                    {STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
                  </select>
                </label>
                <label className="review-field">
                  <span>Review note</span>
                  <textarea
                    className="review-note"
                    value={reviewNote}
                    onChange={(e) => setReviewNote(e.target.value)}
                    placeholder="Add context, decision rationale, or follow-up action."
                    disabled={reviewBusy}
                  />
                </label>
                <div className="review-actions">
                  <button className="btn btn-primary" onClick={saveReview} disabled={reviewBusy}>
                    <i className={`ti ${reviewBusy ? 'ti-loader-2' : 'ti-device-floppy'}`} />
                    {reviewBusy ? 'Saving...' : 'Save Review'}
                  </button>
                  {reviewSaved && <span className="review-success">Saved</span>}
                  {reviewError && <span className="review-error">{reviewError}</span>}
                </div>
                {(current.reviewed_at || current.reviewed_by) && (
                  <div className="review-meta">
                    Last reviewed by {current.reviewed_by || 'unknown'} at {fmtDate(current.reviewed_at)}
                  </div>
                )}
              </div>
            </div>
          )}
          {tab === 'raw' && <JsonBlock data={current} />}
        </div>
      </div>
    </div>
  );
}

export function RunCard({ run }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <SourceBadge value={run.source} />
          <StatusBadge value={run.status} />
        </div>
        <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>{fmtDate(run.ended_at || run.started_at)}</span>
      </div>
      <div style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{run.message || 'Collection run'}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px', padding: '12px', background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}>
        {[['Collected', run.collected], ['Indexed', run.indexed], ['Dupes', run.duplicates_skipped], ['Errors', run.errors], ['Duration', run.duration_seconds ? `${run.duration_seconds}s` : '—']].map(([k, v]) => (
          <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>{k}</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{fmt(v)}</span>
          </div>
        ))}
      </div>
      <button className="btn btn-ghost" style={{ alignSelf: 'flex-start', fontSize: '12px', height: '24px' }} onClick={() => setOpen((x) => !x)}>{open ? 'Hide JSON' : 'Show JSON'}</button>
      {open && <JsonBlock data={run.details || run} />}
    </div>
  );
}

export function HealthCard({ source }) {
  if (!source) return null;
  const status = source.status || 'unknown';
  const isErr = status === 'error';
  const isWarn = status === 'warning';
  const isDisabled = status === 'disabled';
  const iconStatus = isErr ? 'err' : isWarn ? 'warn' : isDisabled ? 'disabled' : 'ok';
  const iconClass = isErr ? 'ti-alert-circle' : isWarn ? 'ti-alert-triangle' : isDisabled ? 'ti-circle-off' : 'ti-circle-check';
  const indexed = source.indexed_count ?? source.indexed_last_scan ?? source.last_indexed;
  const duplicates = source.duplicate_count ?? source.duplicates_skipped ?? source.last_duplicates;
  const errors = source.error_count ?? source.errors ?? source.last_errors;
  const warnings = source.warning_count ?? source.warnings ?? 0;

  return (
    <div className="health-card">
      <div className="health-header">
        <SourceBadge value={source.source} />
        <div className={`health-status ${iconStatus}`}>
          <i className={`ti ${iconClass}`} />
          {source.status || source.last_scan_status || 'ok'}
        </div>
      </div>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', minHeight: '20px' }}>
        {truncate(source.message || source.last_message || source.last_scan_result || 'Operational', 110)}
      </div>
      <div className="health-metrics">
        <div className="health-metric">
          <span className="health-metric-label">Scan result</span>
          <span className="health-metric-value">{source.scan_result || source.last_scan_result || 'unknown'}</span>
        </div>
        <div className="health-metric">
          <span className="health-metric-label">Last scan</span>
          <span className="health-metric-value">{fmtDate(source.last_scan_at || source.last_scan_time)}</span>
        </div>
        <div className="health-metric">
          <span className="health-metric-label">Indexed</span>
          <span className="health-metric-value">{fmt(indexed)}</span>
        </div>
        <div className="health-metric">
          <span className="health-metric-label">Duplicates</span>
          <span className="health-metric-value">{fmt(duplicates)}</span>
        </div>
        <div className="health-metric">
          <span className="health-metric-label">Errors</span>
          <span className={`health-metric-value ${Number(errors || 0) ? 'text-critical' : ''}`}>{fmt(errors)}</span>
        </div>
        <div className="health-metric">
          <span className="health-metric-label">Warnings</span>
          <span className={`health-metric-value ${Number(warnings || 0) ? 'text-medium' : ''}`}>{fmt(warnings)}</span>
        </div>
      </div>
      {source.last_error && <div className="health-error">{source.last_error}</div>}
    </div>
  );
}
