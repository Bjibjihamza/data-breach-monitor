import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { useCollectionState } from '../hooks/useCollectionState.js';
import { useDetections } from '../hooks/useDetections.js';
import { useSourceHealth } from '../hooks/useSourceHealth.js';
import SourceRunPanel from '../components/scan/SourceRunPanel.jsx';
import { fmtDate, fmt, DetectionDrawer, DetectionCards, DetectionPager, ErrorBanner, HealthCard, Loading, RunCard, JsonBlock } from './_shared.jsx';

export default function GitHubPage() {
  const { refreshKey, refresh, setModalOpen } = useOutletContext();
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
  const totalSignals = detections.data?.total ?? rows.length;

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  // Extract GitHub API quota if available
  let quotaPercent = 100;
  let quotaText = "Unknown";
  if (states.length > 0) {
    const s = states[0].state;
    if (s && s.resources && s.resources.core) {
      const core = s.resources.core;
      quotaPercent = (core.remaining / core.limit) * 100;
      quotaText = `${fmt(core.remaining)} / ${fmt(core.limit)}`;
    } else if (s && s.rate && s.rate.limit) {
      quotaPercent = (s.rate.remaining / s.rate.limit) * 100;
      quotaText = `${fmt(s.rate.remaining)} / ${fmt(s.rate.limit)}`;
    }
  }

  return (
    <div className="gh-page">
      <SourceRunPanel source="github" onScanStarted={() => refresh?.()} />
      <style>{`
        .gh-page {
          padding: 20px 26px;
          display: flex;
          flex-direction: column;
          gap: 28px;
          animation: fade-in 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes fade-in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        
        /* Premium Hero Section */
        .gh-hero {
          position: relative;
          background: linear-gradient(135deg, rgba(16, 20, 28, 0.85) 0%, rgba(5, 7, 10, 0.95) 100%);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 36px 48px;
          overflow: hidden;
          box-shadow: 0 20px 40px -10px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.06);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .gh-hero::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.5), transparent);
        }
        .gh-hero::after {
          content: '';
          position: absolute;
          top: -50%; left: -50%; width: 200%; height: 200%;
          background: radial-gradient(circle at 80% 20%, rgba(59, 130, 246, 0.15) 0%, transparent 40%);
          pointer-events: none;
        }
        .gh-hero-content {
          z-index: 1;
        }
        .gh-title {
          font-size: 32px;
          font-weight: 700;
          color: #fff;
          margin-bottom: 12px;
          display: flex;
          align-items: center;
          gap: 14px;
          letter-spacing: -0.5px;
        }
        .gh-title i {
          color: #3b82f6;
          text-shadow: 0 0 20px rgba(59, 130, 246, 0.5);
        }
        .gh-subtitle {
          color: #a3aab8;
          font-size: 15px;
          max-width: 540px;
          line-height: 1.6;
        }
        .gh-pulse {
          display: inline-block;
          width: 8px; height: 8px;
          background: #10b981;
          border-radius: 50%;
          box-shadow: 0 0 12px #10b981;
          animation: pulse 2s infinite;
          margin-left: 4px;
        }
        @keyframes pulse { 
          0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16,185,129,0.7); } 
          70% { transform: scale(1.1); box-shadow: 0 0 0 10px rgba(16,185,129,0); } 
          100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16,185,129,0); } 
        }

        .gh-stats-container {
          display: flex;
          gap: 20px;
          z-index: 1;
        }
        .gh-stat-box {
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 12px;
          padding: 20px 28px;
          min-width: 170px;
          backdrop-filter: blur(12px);
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }
        .gh-stat-box:hover {
          transform: translateY(-4px);
          background: rgba(255,255,255,0.04);
          border-color: rgba(255,255,255,0.1);
          box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
        .gh-stat-value {
          font-size: 28px;
          font-weight: 700;
          color: #fff;
          font-family: var(--font-mono);
          margin-bottom: 4px;
        }
        .gh-stat-label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: #687285;
          font-weight: 600;
        }

        /* 2-Column Grid Layout */
        .gh-layout {
          display: grid;
          grid-template-columns: minmax(0, 2fr) minmax(0, 1.1fr);
          gap: 28px;
          align-items: start;
        }
        
        /* Premium Panels */
        .gh-panel {
          background: rgba(16, 18, 23, 0.5);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 24px -8px rgba(0,0,0,0.5);
          overflow: hidden;
        }
        .gh-panel-header {
          padding: 14px 20px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255,255,255,0.01);
        }
        .gh-panel-title {
          font-size: 15px;
          font-weight: 600;
          color: #edf0f5;
          display: flex;
          align-items: center;
          gap: 10px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .gh-panel-title i {
          color: #687285;
          font-size: 16px;
        }
        .gh-panel-body {
          padding: 24px;
          flex: 1;
        }

        /* Tactical Filter Bar */
        .gh-filter-bar {
          display: flex;
          gap: 16px;
          padding: 16px 24px;
          background: rgba(0,0,0,0.25);
          border-bottom: 1px solid rgba(255,255,255,0.05);
          align-items: center;
          flex-wrap: wrap;
        }
        .gh-filter-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .gh-filter-label {
          font-size: 11px;
          text-transform: uppercase;
          color: #687285;
          font-weight: 600;
          letter-spacing: 0.5px;
        }
        .gh-filter-input {
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          color: #edf0f5;
          padding: 8px 12px;
          border-radius: 6px;
          font-size: 13px;
          transition: all 0.2s;
        }
        .gh-filter-input:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
          background: rgba(255,255,255,0.05);
        }
        .gh-filter-input option {
          background: #101217;
        }

        /* Glowing Quota Bar */
        .gh-quota-bar {
          height: 6px;
          background: rgba(255,255,255,0.05);
          border-radius: 4px;
          overflow: hidden;
          margin-top: 8px;
          box-shadow: inset 0 1px 3px rgba(0,0,0,0.5);
        }
        .gh-quota-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.8s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 0 10px currentColor;
        }
      `}</style>

      <ErrorBanner error={detections.error || runs.error || health.error} />

      {/* Hero Section */}
      <div className="gh-hero">
        <div className="gh-hero-content">
          <h1 className="gh-title">
            <i className="ti ti-brand-github"></i>
            GitHub Intelligence
            <span className="gh-pulse" title="Live Monitoring Active"></span>
          </h1>
          <p className="gh-subtitle">
            Continuous scanning of public repositories, gists, and organizational footprints for exposed secrets, leaked credentials, and intellectual property.
          </p>
        </div>
        <div className="gh-stats-container">
          <div className="gh-stat-box">
            <div className="gh-stat-value">{fmt(totalSignals)}</div>
            <div className="gh-stat-label">Total Exposures</div>
          </div>
          <div className="gh-stat-box">
            <div className="gh-stat-value">{runs.data?.runs ? fmt(runs.data.runs[0]?.indexed || 0) : '—'}</div>
            <div className="gh-stat-label">Last Run Indexed</div>
          </div>
        </div>
      </div>

      <div className="gh-layout">
        {/* Main Left Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          
          <div className="gh-panel">
            <div className="gh-panel-header">
              <div className="gh-panel-title">
                <i className="ti ti-radar"></i> Exposure Signals
              </div>
              <span className="badge badge-outline" style={{ background: 'rgba(59,130,246,0.1)', borderColor: 'rgba(59,130,246,0.3)', color: '#60a5fa' }}>{fmt(totalSignals)} total signals</span>
            </div>
            
            <div className="gh-filter-bar">
              <div className="gh-filter-group">
                <span className="gh-filter-label">Severity</span>
                <select className="gh-filter-input" value={filters.severity || ''} onChange={set('severity')} style={{ width: '130px' }}>
                  <option value="">Any Severity</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
              <div className="gh-filter-group">
                <span className="gh-filter-label">Confidence</span>
                <select className="gh-filter-input" value={filters.confidence || ''} onChange={set('confidence')} style={{ width: '130px' }}>
                  <option value="">Any Confidence</option>
                  <option value="certain">Certain</option>
                  <option value="firm">Firm</option>
                  <option value="tentative">Tentative</option>
                </select>
              </div>
              <div className="gh-filter-group">
                <span className="gh-filter-label">Secret Type</span>
                <input className="gh-filter-input" value={secretType} onChange={(e) => setSecretType(e.target.value)} placeholder="e.g. AWS, RSA, Token" style={{ width: '160px' }} />
              </div>
              <div className="gh-filter-group" style={{ flexGrow: 1, alignItems: 'flex-end' }}>
                <div style={{ position: 'relative', width: '100%', maxWidth: '250px' }}>
                  <i className="ti ti-search" style={{ position: 'absolute', left: '12px', top: '9px', color: '#687285', fontSize: '14px' }} />
                  <input 
                    className="gh-filter-input" 
                    value={filters.search || ''} 
                    onChange={set('search')} 
                    placeholder="Search keywords..." 
                    style={{ width: '100%', paddingLeft: '34px' }} 
                  />
                </div>
              </div>
            </div>

            <div className="gh-panel-body" style={{ padding: '0', background: 'rgba(0,0,0,0.15)' }}>
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
            <div className="gh-panel">
              <div className="gh-panel-header">
                <div className="gh-panel-title">
                  <i className="ti ti-heartbeat"></i> Scanner Health
                </div>
              </div>
              <div className="gh-panel-body" style={{ padding: '20px' }}>
                <HealthCard source={src} />
              </div>
            </div>
          )}

          <div className="gh-panel">
            <div className="gh-panel-header">
              <div className="gh-panel-title">
                <i className="ti ti-api"></i> API Quota & State
              </div>
            </div>
            <div className="gh-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            

              {states.map((item) => (
                <div key={item.id || item.key} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong style={{ fontSize: '12px', color: '#a3aab8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{item.key}</strong>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: '#687285' }}>{fmtDate(item.updated_at)}</span>
                  </div>
                  <JsonBlock data={item.state} />
                </div>
              ))}
              {states.length === 0 && <div style={{ color: '#687285', fontSize: '13px', fontStyle: 'italic' }}>No state data available.</div>}
            </div>
          </div>

          <div className="gh-panel">
            <div className="gh-panel-header">
              <div className="gh-panel-title">
                <i className="ti ti-history"></i> Recent Runs
              </div>
            </div>
            <div className="gh-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
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
