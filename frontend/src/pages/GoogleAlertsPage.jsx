import { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { useCollectionState } from '../hooks/useCollectionState.js';
import { useDetections } from '../hooks/useDetections.js';
import { useSourceHealth } from '../hooks/useSourceHealth.js';
import SourceRunPanel from '../components/scan/SourceRunPanel.jsx';
import { fmtDate, fmt, DetectionDrawer, DetectionCards, DetectionPager, ErrorBanner, HealthCard, Loading, RunCard, truncate } from './_shared.jsx';

export default function GoogleAlertsPage() {
  const { refreshKey, refresh, setModalOpen } = useOutletContext();
  const [filters, setFilters] = useState({ source: 'google_alerts' });
  const [selected, setSelected] = useState(null);

  const detections = useDetections(filters, refreshKey);
  const runs = useCollectionRuns({ source: 'google_alerts', limit: 10 }, refreshKey);
  const health = useSourceHealth(refreshKey);
  const state = useCollectionState(refreshKey);

  useEffect(() => {
    setModalOpen(Boolean(selected));
    return () => setModalOpen(false);
  }, [selected, setModalOpen]);

  const src = (health.data?.sources || []).find((s) => s.source === 'google_alerts');
  const states = (state.data?.states || []).filter((s) => s.source === 'google_alerts');
  const latestDetails = runs.data?.runs?.[0]?.details || {};
  const rows = useMemo(() => detections.data?.detections || [], [detections.data]);
  const totalSignals = detections.data?.total ?? rows.length;

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="ga-page">
      <SourceRunPanel source="google_alerts" onScanStarted={() => refresh?.()} />
      <style>{`
        .ga-page {
          padding: 20px 26px;
          display: flex;
          flex-direction: column;
          gap: 20px;
          animation: fade-in 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes fade-in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        
        /* Premium Hero Section */
        .ga-hero {
          position: relative;
          background: linear-gradient(135deg, rgba(16, 28, 26, 0.85) 0%, rgba(8, 14, 13, 0.95) 100%);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 30px 40px;
          overflow: hidden;
          box-shadow: 0 20px 40px -10px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.06);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .ga-hero::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, rgba(20, 184, 166, 0.5), transparent);
        }
        .ga-hero::after {
          content: '';
          position: absolute;
          top: -50%; left: -50%; width: 200%; height: 200%;
          background: radial-gradient(circle at 80% 20%, rgba(20, 184, 166, 0.12) 0%, transparent 40%);
          pointer-events: none;
        }
        .ga-hero-content {
          z-index: 1;
        }
        .ga-title {
          font-size: 32px;
          font-weight: 700;
          color: #fff;
          margin-bottom: 12px;
          display: flex;
          align-items: center;
          gap: 14px;
          letter-spacing: -0.5px;
        }
        .ga-title i {
          color: #14b8a6;
          text-shadow: 0 0 20px rgba(20, 184, 166, 0.5);
        }
        .ga-subtitle {
          color: #a3aab8;
          font-size: 15px;
          max-width: 540px;
          line-height: 1.6;
        }
        .ga-pulse {
          display: inline-block;
          width: 8px; height: 8px;
          background: #14b8a6;
          border-radius: 50%;
          box-shadow: 0 0 12px #14b8a6;
          animation: pulse-ga 2s infinite;
          margin-left: 4px;
        }
        @keyframes pulse-ga { 
          0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.7); } 
          70% { transform: scale(1.1); box-shadow: 0 0 0 10px rgba(20, 184, 166, 0); } 
          100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(20, 184, 166, 0); } 
        }

        .ga-stats-container {
          display: flex;
          gap: 20px;
          z-index: 1;
        }
        .ga-stat-box {
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          padding: 20px 28px;
          min-width: 170px;
          backdrop-filter: blur(12px);
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        .ga-stat-box:hover {
          transform: translateY(-4px);
          background: rgba(255,255,255,0.04);
          border-color: rgba(255,255,255,0.1);
          box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
        .ga-stat-value {
          font-size: 28px;
          font-weight: 700;
          color: #fff;
          font-family: var(--font-mono);
          margin-bottom: 4px;
        }
        .ga-stat-label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: #687285;
          font-weight: 600;
        }

        /* 2-Column Grid Layout */
        .ga-layout {
          display: grid;
          grid-template-columns: minmax(0, 2fr) minmax(0, 1.1fr);
          gap: 28px;
          align-items: start;
        }
        
        /* Premium Panels */
        .ga-panel {
          background: rgba(16, 20, 19, 0.5);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 24px -8px rgba(0,0,0,0.5);
          overflow: hidden;
        }
        .ga-panel-header {
          padding: 20px 24px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255,255,255,0.01);
        }
        .ga-panel-title {
          font-size: 15px;
          font-weight: 600;
          color: #edf0f5;
          display: flex;
          align-items: center;
          gap: 10px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .ga-panel-title i {
          color: #687285;
          font-size: 16px;
        }
        .ga-panel-body {
          padding: 24px;
          flex: 1;
        }

        /* Tactical Filter Bar */
        .ga-filter-bar {
          display: flex;
          gap: 16px;
          padding: 16px 24px;
          background: rgba(0,0,0,0.25);
          border-bottom: 1px solid rgba(255,255,255,0.05);
          align-items: center;
          flex-wrap: wrap;
        }
        .ga-filter-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .ga-filter-label {
          font-size: 11px;
          text-transform: uppercase;
          color: #687285;
          font-weight: 600;
          letter-spacing: 0.5px;
        }
        .ga-filter-input {
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          color: #edf0f5;
          padding: 8px 12px;
          border-radius: 6px;
          font-size: 13px;
          transition: all 0.2s;
        }
        .ga-filter-input:focus {
          border-color: #14b8a6;
          box-shadow: 0 0 0 3px rgba(20, 184, 166, 0.15);
          background: rgba(255,255,255,0.05);
        }
        .ga-filter-input option {
          background: #101217;
        }
        
        .ga-feed-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.04);
          border-radius: 8px;
          transition: background 0.2s;
        }
        .ga-feed-item:hover {
          background: rgba(255,255,255,0.04);
        }
        
        /* Metric Cards */
        .ga-metric-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 16px;
        }
        .ga-metric-card {
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.04);
          border-radius: 8px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .ga-metric-label {
          font-size: 11px;
          text-transform: uppercase;
          color: #a3aab8;
          letter-spacing: 0.5px;
        }
        .ga-metric-value {
          font-size: 24px;
          font-weight: 700;
          color: #edf0f5;
          font-family: var(--font-mono);
        }
      `}</style>

      <ErrorBanner error={detections.error || runs.error || health.error} />

      {/* Hero Section */}
      <div className="ga-hero">
        <div className="ga-hero-content">
          <h1 className="ga-title">
            <i className="ti ti-rss"></i>
            News Intelligence
            <span className="ga-pulse" title="Live Monitoring Active"></span>
          </h1>
          <p className="ga-subtitle">
            Aggregating OSINT reports, public data breach announcements, and media coverage across targeted RSS feeds and search alerts.
          </p>
        </div>
        <div className="ga-stats-container">
          <div className="ga-stat-box">
            <div className="ga-stat-value">{fmt(totalSignals)}</div>
            <div className="ga-stat-label">Feed Matches</div>
          </div>
          <div className="ga-stat-box">
            <div className="ga-stat-value">{fmt(latestDetails.new_feed_entries ?? 0)}</div>
            <div className="ga-stat-label">New Entries (Latest Run)</div>
          </div>
        </div>
      </div>

      <div className="ga-layout">
        {/* Main Left Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          
          <div className="ga-panel">
            <div className="ga-panel-header">
              <div className="ga-panel-title">
                <i className="ti ti-article"></i> Intelligence Feed
              </div>
              <span className="badge badge-outline" style={{ background: 'rgba(20, 184, 166, 0.1)', borderColor: 'rgba(20, 184, 166, 0.3)', color: '#5eead4' }}>{fmt(totalSignals)} total articles</span>
            </div>
            
            <div className="ga-filter-bar">
              <div className="ga-filter-group">
                <span className="ga-filter-label">Category</span>
                <input className="ga-filter-input" value={filters.category || ''} onChange={set('category')} placeholder="e.g. breach" style={{ width: '130px' }} />
              </div>
              <div className="ga-filter-group">
                <span className="ga-filter-label">Country</span>
                <input className="ga-filter-input" value={filters.country || ''} onChange={set('country')} placeholder="e.g. France" style={{ width: '110px' }} />
              </div>
              <div className="ga-filter-group">
                <span className="ga-filter-label">Severity</span>
                <select className="ga-filter-input" value={filters.severity || ''} onChange={set('severity')} style={{ width: '130px' }}>
                  <option value="">Any Severity</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
              <div className="ga-filter-group" style={{ flexGrow: 1, alignItems: 'flex-end' }}>
                <div style={{ position: 'relative', width: '100%', maxWidth: '250px' }}>
                  <i className="ti ti-search" style={{ position: 'absolute', left: '12px', top: '9px', color: '#687285', fontSize: '14px' }} />
                  <input 
                    className="ga-filter-input" 
                    value={filters.search || ''} 
                    onChange={set('search')} 
                    placeholder="Search keywords..." 
                    style={{ width: '100%', paddingLeft: '34px' }} 
                  />
                </div>
              </div>
            </div>

            <div className="ga-panel-body" style={{ padding: '0', background: 'rgba(0,0,0,0.15)' }}>
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
            <div className="ga-panel">
              <div className="ga-panel-header">
                <div className="ga-panel-title">
                  <i className="ti ti-heartbeat"></i> Scanner Health
                </div>
              </div>
              <div className="ga-panel-body" style={{ padding: '20px' }}>
                <HealthCard source={src} />
              </div>
            </div>
          )}

          <div className="ga-panel">
            <div className="ga-panel-header">
              <div className="ga-panel-title">
                <i className="ti ti-chart-bar"></i> Feed Counters
              </div>
            </div>
            <div className="ga-panel-body" style={{ padding: '20px' }}>
              <div className="ga-metric-grid">
                <div className="ga-metric-card">
                  <div className="ga-metric-label">New Entries</div>
                  <div className="ga-metric-value" style={{ color: '#5eead4' }}>{fmt(latestDetails.new_feed_entries ?? 0)}</div>
                </div>
                <div className="ga-metric-card">
                  <div className="ga-metric-label">Known Entries</div>
                  <div className="ga-metric-value">{fmt(latestDetails.known_feed_entries ?? 0)}</div>
                </div>
              </div>
            </div>
          </div>

          <div className="ga-panel">
            <div className="ga-panel-header">
              <div className="ga-panel-title">
                <i className="ti ti-list"></i> Tracked Feeds State
              </div>
            </div>
            <div className="ga-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {states.length > 0 ? states.map((item) => (
                <div key={item.id || item.key} className="ga-feed-item">
                  <span style={{ fontSize: '13px', color: '#edf0f5', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <i className="ti ti-rss" style={{ color: '#14b8a6' }}></i>
                    {truncate(item.key, 30)}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: '#687285', textAlign: 'right' }}>
                    {fmtDate(item.updated_at)}
                  </span>
                </div>
              )) : <div style={{ color: '#687285', fontSize: '13px', fontStyle: 'italic' }}>No feed state tracked yet.</div>}
            </div>
          </div>

          <div className="ga-panel">
            <div className="ga-panel-header">
              <div className="ga-panel-title">
                <i className="ti ti-history"></i> Recent Runs
              </div>
            </div>
            <div className="ga-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
