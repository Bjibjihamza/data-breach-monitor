import { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { useCollectionState } from '../hooks/useCollectionState.js';
import { useDetections } from '../hooks/useDetections.js';
import { useSourceHealth } from '../hooks/useSourceHealth.js';
import { fmtDate, fmt, DetectionDrawer, DetectionCards, ErrorBanner, HealthCard, Loading, RunCard, truncate } from './_shared.jsx';

export default function TelegramPage() {
  const { refreshKey, setModalOpen } = useOutletContext();
  const [filters, setFilters] = useState({ source: 'telegram' });
  const [channel, setChannel] = useState('');
  const [selected, setSelected] = useState(null);

  const detections = useDetections(filters, refreshKey);
  const runs = useCollectionRuns({ source: 'telegram', limit: 10 }, refreshKey);
  const health = useSourceHealth(refreshKey);
  const state = useCollectionState(refreshKey);

  useEffect(() => {
    setModalOpen(Boolean(selected));
    return () => setModalOpen(false);
  }, [selected, setModalOpen]);

  const src = (health.data?.sources || []).find((s) => s.source === 'telegram');
  const states = (state.data?.states || []).filter((s) => s.source === 'telegram');
  const rows = useMemo(() => {
    const all = detections.data?.detections || [];
    if (!channel) return all;
    return all.filter((r) => String(r.channel_name || r.channel_username || '').toLowerCase().includes(channel.toLowerCase()));
  }, [detections.data, channel]);

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Telegram Intelligence</h1>
          <p className="page-subtitle">Underground channels, OSINT signals, and CVE discussions</p>
        </div>
      </div>

      <ErrorBanner error={detections.error || runs.error || health.error} />

      {src && (
        <div style={{ marginBottom: '8px' }}>
          <HealthCard source={src} />
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <span className="card-title">Channel Activity Stream</span>
          <span className="card-subtitle">{fmt(rows.length)} matches found</span>
        </div>
        <div className="filters-bar" style={{ borderTop: 'none', borderBottom: '1px solid var(--border-subtle)', borderRadius: 0 }}>
          <div className="filter-group">
            <span className="filter-label">Channel</span>
            <input className="filter-input" value={channel} onChange={(e) => setChannel(e.target.value)} placeholder="filter…" style={{ width: '120px' }} />
          </div>
          <div className="filter-group">
            <span className="filter-label">Severity</span>
            <input className="filter-input" value={filters.severity || ''} onChange={set('severity')} placeholder="any" style={{ width: '100px' }} />
          </div>
          <div className="filter-group">
            <span className="filter-label">Confidence</span>
            <input className="filter-input" value={filters.confidence || ''} onChange={set('confidence')} placeholder="any" style={{ width: '100px' }} />
          </div>
          <div className="filter-group" style={{ flexGrow: 1, justifyContent: 'flex-end' }}>
            <div style={{ position: 'relative' }}>
              <i className="ti ti-search" style={{ position: 'absolute', left: '10px', top: '8px', color: 'var(--text-tertiary)', fontSize: '14px' }} />
              <input 
                className="filter-input" 
                value={filters.search || ''} 
                onChange={set('search')} 
                placeholder="CVE or keyword..." 
                style={{ width: '200px', paddingLeft: '32px' }} 
              />
            </div>
          </div>
        </div>

        <div className="card-body">
          {detections.loading && <Loading />}
          {!detections.loading && <DetectionCards detections={rows} onSelect={setSelected} />}
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><span className="card-title">Recent Collection Runs</span></div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {(runs.data?.runs || []).slice(0, 3).map((r) => <RunCard key={r.run_id || r.id} run={r} />)}
            {(!runs.data?.runs || runs.data?.runs.length === 0) && <div style={{ color: 'var(--text-tertiary)' }}>No recent runs.</div>}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Channel Watchlist State</span></div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {states.length > 0 ? states.map((item) => (
              <div key={item.id || item.key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '8px', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>{item.key}</span>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-secondary)' }}>
                    msg ID: {item.last_seen_message_id ?? item.state?.last_seen_message_id ?? '—'}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)' }}>
                    {fmtDate(item.updated_at)}
                  </span>
                </div>
              </div>
            )) : <div style={{ color: 'var(--text-tertiary)' }}>No channel state tracked yet.</div>}
          </div>
        </div>
      </div>

      <DetectionDrawer detection={selected} onClose={() => setSelected(null)} onUpdated={setSelected} />
    </div>
  );
}
