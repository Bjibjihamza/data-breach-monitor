import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { useCollectionState } from '../hooks/useCollectionState.js';
import { useDetections } from '../hooks/useDetections.js';
import { useSourceHealth } from '../hooks/useSourceHealth.js';
import { fmtDate, fmt, DetectionDrawer, DetectionCards, ErrorBanner, HealthCard, Loading, RunCard, JsonBlock } from './_shared.jsx';

export default function GitHubPage() {
  const { refreshKey, setModalOpen } = useOutletContext();
  const [filters, setFilters] = useState({ source: 'github' });
  const [secretType, setSecretType] = useState('');
  const [selected, setSelected] = useState(null);

  const detections = useDetections(filters, refreshKey);
  const runs = useCollectionRuns({ source: 'github', limit: 10 }, refreshKey);
  const health = useSourceHealth(refreshKey);
  const state = useCollectionState(refreshKey);

  useEffect(() => {
    setModalOpen(Boolean(selected));
    return () => setModalOpen(false);
  }, [selected, setModalOpen]);

  const src = (health.data?.sources || []).find((s) => s.source === 'github');
  const states = (state.data?.states || []).filter((s) => s.source === 'github');
  const rows = (detections.data?.detections || []).filter((r) =>
    !secretType || (r.secret_types || []).some((t) => t.toLowerCase().includes(secretType.toLowerCase()))
  );

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Global Exposure Monitoring</h1>
          <p className="page-subtitle">Global risk profiles for exposed secrets, leaked credentials, and risky public code</p>
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
          <span className="card-title">Exposure Signals</span>
          <span className="card-subtitle">{fmt(rows.length)} matches found</span>
        </div>
        <div className="filters-bar" style={{ borderTop: 'none', borderBottom: '1px solid var(--border-subtle)', borderRadius: 0 }}>
          <div className="filter-group">
            <span className="filter-label">Severity</span>
            <input className="filter-input" value={filters.severity || ''} onChange={set('severity')} placeholder="any" style={{ width: '100px' }} />
          </div>
          <div className="filter-group">
            <span className="filter-label">Confidence</span>
            <input className="filter-input" value={filters.confidence || ''} onChange={set('confidence')} placeholder="any" style={{ width: '100px' }} />
          </div>
          <div className="filter-group">
            <span className="filter-label">Secret Type</span>
            <input className="filter-input" value={secretType} onChange={(e) => setSecretType(e.target.value)} placeholder="e.g. aws" style={{ width: '120px' }} />
          </div>
          <div className="filter-group" style={{ flexGrow: 1, justifyContent: 'flex-end' }}>
            <div style={{ position: 'relative' }}>
              <i className="ti ti-search" style={{ position: 'absolute', left: '10px', top: '8px', color: 'var(--text-tertiary)', fontSize: '14px' }} />
              <input 
                className="filter-input" 
                value={filters.search || ''} 
                onChange={set('search')} 
                placeholder="Search..." 
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
          <div className="card-header"><span className="card-title">API Quota & State</span></div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {states.map((item) => (
              <div key={item.id || item.key} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{item.key}</strong>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)' }}>Updated {fmtDate(item.updated_at)}</span>
                </div>
                <JsonBlock data={item.state} />
              </div>
            ))}
            {states.length === 0 && <div style={{ color: 'var(--text-tertiary)' }}>No state data available.</div>}
          </div>
        </div>
      </div>

      <DetectionDrawer detection={selected} onClose={() => setSelected(null)} onUpdated={setSelected} />
    </div>
  );
}
