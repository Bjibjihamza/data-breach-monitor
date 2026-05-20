import { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { useCollectionState } from '../hooks/useCollectionState.js';
import { useDetections } from '../hooks/useDetections.js';
import { useSourceHealth } from '../hooks/useSourceHealth.js';
import SourceRunPanel from '../components/scan/SourceRunPanel.jsx';
import { fmtDate, fmt, DetectionDrawer, DetectionCards, DetectionPager, ErrorBanner, HealthCard, Loading, RunCard, truncate } from './_shared.jsx';

export default function TelegramPage() {
  const { refreshKey, refresh, setModalOpen } = useOutletContext();
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
  const totalSignals = detections.data?.total ?? rows.length;

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="tg-page">
      <SourceRunPanel source="telegram" onScanStarted={() => refresh?.()} />
      <style>{`
        .tg-page {
          padding: 14px 20px;
          display: flex;
          flex-direction: column;
          gap: 20px;
          animation: fade-in 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes fade-in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        
        /* Premium Hero Section */
        .tg-hero {
          position: relative;
          background: linear-gradient(135deg, rgba(18, 16, 28, 0.85) 0%, rgba(9, 7, 13, 0.95) 100%);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 30px 40px;
          overflow: hidden;
          box-shadow: 0 20px 40px -10px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.06);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .tg-hero::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.5), transparent);
        }
        .tg-hero::after {
          content: '';
          position: absolute;
          top: -50%; left: -50%; width: 200%; height: 200%;
          background: radial-gradient(circle at 80% 20%, rgba(139, 92, 246, 0.15) 0%, transparent 40%);
          pointer-events: none;
        }
        .tg-hero-content {
          z-index: 1;
        }
        .tg-title {
          font-size: 32px;
          font-weight: 700;
          color: #fff;
          margin-bottom: 12px;
          display: flex;
          align-items: center;
          gap: 14px;
          letter-spacing: -0.5px;
        }
        .tg-title i {
          color: #8b5cf6;
          text-shadow: 0 0 20px rgba(139, 92, 246, 0.5);
        }
        .tg-subtitle {
          color: #a3aab8;
          font-size: 15px;
          max-width: 540px;
          line-height: 1.6;
        }
        .tg-pulse {
          display: inline-block;
          width: 8px; height: 8px;
          background: #10b981;
          border-radius: 50%;
          box-shadow: 0 0 12px #10b981;
          animation: pulse 2s infinite;
          margin-left: 4px;
        }

        .tg-stats-container {
          display: flex;
          gap: 20px;
          z-index: 1;
        }
        .tg-stat-box {
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          padding: 20px 28px;
          min-width: 170px;
          backdrop-filter: blur(12px);
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        .tg-stat-box:hover {
          transform: translateY(-4px);
          background: rgba(255,255,255,0.04);
          border-color: rgba(255,255,255,0.1);
          box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
        .tg-stat-value {
          font-size: 28px;
          font-weight: 700;
          color: #fff;
          font-family: var(--font-mono);
          margin-bottom: 4px;
        }
        .tg-stat-label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: #687285;
          font-weight: 600;
        }

        /* 2-Column Grid Layout */
        .tg-layout {
          display: grid;
          grid-template-columns: minmax(0, 2fr) minmax(0, 1.1fr);
          gap: 28px;
          align-items: start;
        }
        
        /* Premium Panels */
        .tg-panel {
          background: rgba(18, 16, 23, 0.5);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 24px -8px rgba(0,0,0,0.5);
          overflow: hidden;
        }
        .tg-panel-header {
          padding: 20px 24px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255,255,255,0.01);
        }
        .tg-panel-title {
          font-size: 15px;
          font-weight: 600;
          color: #edf0f5;
          display: flex;
          align-items: center;
          gap: 10px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .tg-panel-title i {
          color: #687285;
          font-size: 16px;
        }
        .tg-panel-body {
          padding: 24px;
          flex: 1;
        }

        /* Tactical Filter Bar */
        .tg-filter-bar {
          display: flex;
          gap: 16px;
          padding: 16px 24px;
          background: rgba(0,0,0,0.25);
          border-bottom: 1px solid rgba(255,255,255,0.05);
          align-items: center;
          flex-wrap: wrap;
        }
        .tg-filter-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .tg-filter-label {
          font-size: 11px;
          text-transform: uppercase;
          color: #687285;
          font-weight: 600;
          letter-spacing: 0.5px;
        }
        .tg-filter-input {
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          color: #edf0f5;
          padding: 8px 12px;
          border-radius: 6px;
          font-size: 13px;
          transition: all 0.2s;
        }
        .tg-filter-input:focus {
          border-color: #8b5cf6;
          box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15);
          background: rgba(255,255,255,0.05);
        }
        .tg-filter-input option {
          background: #101217;
        }
        
        .tg-watchlist-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.04);
          border-radius: 8px;
          transition: background 0.2s;
        }
        .tg-watchlist-item:hover {
          background: rgba(255,255,255,0.04);
        }
      `}</style>

      <ErrorBanner error={detections.error || runs.error || health.error} />

      {/* Hero Section */}
      <div className="tg-hero">
        <div className="tg-hero-content">
          <h1 className="tg-title">
            <i className="ti ti-brand-telegram"></i>
            Telegram Intelligence
            <span className="tg-pulse" title="Live Monitoring Active"></span>
          </h1>
          <p className="tg-subtitle">
            Monitoring underground channels, OSINT communities, and threat actor discussions for early warning signals and CVE mentions.
          </p>
        </div>
        <div className="tg-stats-container">
          <div className="tg-stat-box">
            <div className="tg-stat-value">{fmt(totalSignals)}</div>
            <div className="tg-stat-label">Total Signals</div>
          </div>
          <div className="tg-stat-box">
            <div className="tg-stat-value">{fmt(states.length)}</div>
            <div className="tg-stat-label">Channels Watched</div>
          </div>
        </div>
      </div>

      <div className="tg-layout">
        {/* Main Left Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          
          <div className="tg-panel">
            <div className="tg-panel-header">
              <div className="tg-panel-title">
                <i className="ti ti-message-2"></i> Channel Activity Stream
              </div>
              <span className="badge badge-outline" style={{ background: 'rgba(139, 92, 246, 0.1)', borderColor: 'rgba(139, 92, 246, 0.3)', color: '#a78bfa' }}>{fmt(totalSignals)} total matches</span>
            </div>
            
            <div className="tg-filter-bar">
              <div className="tg-filter-group">
                <span className="tg-filter-label">Channel</span>
                <input className="tg-filter-input" value={channel} onChange={(e) => setChannel(e.target.value)} placeholder="e.g. vxunderground" style={{ width: '150px' }} />
              </div>
              <div className="tg-filter-group">
                <span className="tg-filter-label">Severity</span>
                <select className="tg-filter-input" value={filters.severity || ''} onChange={set('severity')} style={{ width: '130px' }}>
                  <option value="">Any Severity</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
              <div className="tg-filter-group">
                <span className="tg-filter-label">Confidence</span>
                <select className="tg-filter-input" value={filters.confidence || ''} onChange={set('confidence')} style={{ width: '130px' }}>
                  <option value="">Any Confidence</option>
                  <option value="certain">Certain</option>
                  <option value="firm">Firm</option>
                  <option value="tentative">Tentative</option>
                </select>
              </div>
              <div className="tg-filter-group" style={{ flexGrow: 1, alignItems: 'flex-end' }}>
                <div style={{ position: 'relative', width: '100%', maxWidth: '250px' }}>
                  <i className="ti ti-search" style={{ position: 'absolute', left: '12px', top: '9px', color: '#687285', fontSize: '14px' }} />
                  <input 
                    className="tg-filter-input" 
                    value={filters.search || ''} 
                    onChange={set('search')} 
                    placeholder="Search keywords, CVE..." 
                    style={{ width: '100%', paddingLeft: '34px' }} 
                  />
                </div>
              </div>
            </div>

            <div className="tg-panel-body" style={{ padding: '0', background: 'rgba(0,0,0,0.15)' }}>
              {detections.loading && <Loading />}
              {!detections.loading && (
                <div style={{ padding: '24px' }}>
                  <DetectionCards detections={rows} onSelect={setSelected} />
                  <DetectionPager
                    data={detections.data}
                    loadingMore={detections.loadingMore}
                    onLoadMore={detections.loadMore}
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Right Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          
          {src && (
            <div className="tg-panel">
              <div className="tg-panel-header">
                <div className="tg-panel-title">
                  <i className="ti ti-heartbeat"></i> Scanner Health
                </div>
              </div>
              <div className="tg-panel-body" style={{ padding: '20px' }}>
                <HealthCard source={src} />
              </div>
            </div>
          )}

          <div className="tg-panel">
            <div className="tg-panel-header">
              <div className="tg-panel-title">
                <i className="ti ti-list"></i> Watchlist State
              </div>
            </div>
            <div className="tg-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {states.length > 0 ? states.map((item) => (
                <div key={item.id || item.key} className="tg-watchlist-item">
                  <span style={{ fontSize: '13px', color: '#edf0f5', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <i className="ti ti-hash" style={{ color: '#687285' }}></i>
                    {item.key}
                  </span>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: '#8b5cf6', background: 'rgba(139, 92, 246, 0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                      MSG ID: {item.last_seen_message_id ?? item.state?.last_seen_message_id ?? '—'}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: '#687285' }}>
                      {fmtDate(item.updated_at)}
                    </span>
                  </div>
                </div>
              )) : <div style={{ color: '#687285', fontSize: '13px', fontStyle: 'italic' }}>No channel state tracked yet.</div>}
            </div>
          </div>

          <div className="tg-panel">
            <div className="tg-panel-header">
              <div className="tg-panel-title">
                <i className="ti ti-history"></i> Recent Runs
              </div>
            </div>
            <div className="tg-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {(runs.data?.runs || []).slice(0, 3).map((r) => <RunCard key={r.run_id || r.id} run={r} />)}
              {(!runs.data?.runs || runs.data?.runs.length === 0) && <div style={{ color: '#687285', fontSize: '13px', fontStyle: 'italic' }}>No recent runs.</div>}
            </div>
          </div>
          
        </div>
      </div>

      <DetectionDrawer detection={selected} onClose={() => setSelected(null)} onUpdated={setSelected} />
    </div>
  );
}
