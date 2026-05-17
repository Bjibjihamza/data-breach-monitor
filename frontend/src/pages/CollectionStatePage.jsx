import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useCollectionState } from '../hooks/useCollectionState.js';
import { Empty, ErrorBanner, JsonBlock, SourceBadge, fmtDate } from './_shared.jsx';

function StateCard({ item, onRaw }) {
  const s = item.state || {};
  return (
    <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <SourceBadge value={item.source} />
          <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{item.key}</strong>
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)' }}>
          Updated: {fmtDate(item.updated_at)}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', padding: '12px', background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)' }}>
        {item.source === 'github' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Query Window</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontSize: '12px' }}>{s.query_window_start ?? '—'} → {s.query_window_end ?? '—'}</span>
          </div>
        )}
        {item.source === 'telegram' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Last Message ID</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontSize: '12px' }}>{s.last_seen_message_id ?? item.last_seen_message_id ?? '—'}</span>
          </div>
        )}
        {item.source === 'google_alerts' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Known Hashes</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontSize: '12px' }}>{Array.isArray(s.known_entry_hashes) ? s.known_entry_hashes.length : item.known_entry_hashes_count ?? '—'}</span>
          </div>
        )}
      </div>

      <button className="btn btn-outline" style={{ alignSelf: 'flex-start', fontSize: '12px', height: '28px' }} onClick={() => onRaw(item)}>
        <i className="ti ti-code" /> View Raw JSON
      </button>
    </div>
  );
}

export default function CollectionStatePage() {
  const { refreshKey, setModalOpen } = useOutletContext();
  const [rawItem, setRawItem] = useState(null);
  const state = useCollectionState(refreshKey);
  const states = state.data?.states || [];

  useEffect(() => () => setModalOpen(false), [setModalOpen]);

  const openRaw = (item) => { setRawItem(item); setModalOpen(true); };
  const closeRaw = () => { setRawItem(null); setModalOpen(false); };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Collection State Tracker</h1>
          <p className="page-subtitle">Incremental window states and API progress markers</p>
        </div>
      </div>

      <ErrorBanner error={state.error} />

      <div className="card">
        <div className="card-header">
          <span className="card-title">State Summary</span>
          <span className="card-subtitle">{states.length} active tracker entries</span>
        </div>
        <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '16px' }}>
          {states.map((item) => (
            <StateCard key={item.id || `${item.source}-${item.key}`} item={item} onRaw={openRaw} />
          ))}
          {!states.length && <Empty title="No collection state" sub="State appears after incremental collectors run." />}
        </div>
      </div>

      {rawItem && (
        <div className="drawer-backdrop" onMouseDown={closeRaw}>
          <div className="drawer" onMouseDown={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <div className="drawer-top">
                <h2 className="drawer-title">Raw State Payload</h2>
                <button className="drawer-close" onClick={closeRaw}><i className="ti ti-x" style={{ fontSize: '20px' }} /></button>
              </div>
              <div className="drawer-meta">
                <SourceBadge value={rawItem.source} />
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{rawItem.key}</span>
              </div>
            </div>
            <div className="drawer-body">
              <div className="drawer-section">
                <div className="drawer-section-title">Internal JSON</div>
                <JsonBlock data={rawItem} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}