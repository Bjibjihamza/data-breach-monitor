import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useCollectionRuns } from '../hooks/useCollectionRuns.js';
import { SOURCES } from '../utils/constants.js';
import { BarChart, Empty, ErrorBanner, RunCard } from './_shared.jsx';

export default function CollectionRunsPage() {
  const { refreshKey } = useOutletContext();
  const [filters, setFilters] = useState({ limit: 50 });
  const runs = useCollectionRuns(filters, refreshKey);
  const rows = runs.data?.runs || [];

  const chartData = rows.slice(0, 12).reverse().map((r) => ({
    label: r.source,
    value: Number(r.indexed || 0),
    count: Number(r.indexed || 0),
  }));

  return (
    <div className="cr-page">
      <style>{`
        .cr-page {
          padding: 28px 32px;
          display: flex;
          flex-direction: column;
          gap: 28px;
          animation: fade-in 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes fade-in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        
        /* Premium Hero Section */
        .cr-hero {
          position: relative;
          background: linear-gradient(135deg, rgba(23, 25, 35, 0.85) 0%, rgba(12, 14, 20, 0.95) 100%);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          padding: 36px 48px;
          overflow: hidden;
          box-shadow: 0 20px 40px -10px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.06);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .cr-hero::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, rgba(167, 139, 250, 0.5), transparent);
        }
        .cr-hero-content {
          z-index: 1;
        }
        .cr-title {
          font-size: 32px;
          font-weight: 700;
          color: #fff;
          margin-bottom: 12px;
          display: flex;
          align-items: center;
          gap: 14px;
          letter-spacing: -0.5px;
        }
        .cr-title i {
          color: #a78bfa;
          text-shadow: 0 0 20px rgba(167, 139, 250, 0.5);
        }
        .cr-subtitle {
          color: #a3aab8;
          font-size: 15px;
          max-width: 540px;
          line-height: 1.6;
        }

        /* 2-Column Grid Layout */
        .cr-layout {
          display: grid;
          grid-template-columns: minmax(0, 2fr) minmax(0, 1.1fr);
          gap: 28px;
          align-items: start;
        }
        
        /* Premium Panels */
        .cr-panel {
          background: rgba(16, 20, 19, 0.5);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 24px -8px rgba(0,0,0,0.5);
          overflow: hidden;
        }
        .cr-panel-header {
          padding: 20px 24px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(255,255,255,0.01);
        }
        .cr-panel-title {
          font-size: 15px;
          font-weight: 600;
          color: #edf0f5;
          display: flex;
          align-items: center;
          gap: 10px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .cr-panel-title i {
          color: #a78bfa;
          font-size: 16px;
        }
        .cr-panel-body {
          padding: 24px;
          flex: 1;
        }

        /* Tactical Filter Bar */
        .cr-filter-bar {
          display: flex;
          gap: 16px;
          padding: 16px 24px;
          background: rgba(0,0,0,0.25);
          border-bottom: 1px solid rgba(255,255,255,0.05);
          align-items: center;
          flex-wrap: wrap;
        }
        .cr-filter-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .cr-filter-label {
          font-size: 11px;
          text-transform: uppercase;
          color: #687285;
          font-weight: 600;
          letter-spacing: 0.5px;
        }
        .cr-filter-input {
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          color: #edf0f5;
          padding: 8px 12px;
          border-radius: 6px;
          font-size: 13px;
          transition: all 0.2s;
        }
        .cr-filter-input:focus {
          border-color: #a78bfa;
          box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.15);
          background: rgba(255,255,255,0.05);
        }
        .cr-filter-input option {
          background: #101217;
        }
      `}</style>

      <ErrorBanner error={runs.error} />

      {/* Hero Section */}
      <div className="cr-hero">
        <div className="cr-hero-content">
          <h1 className="cr-title">
            <i className="ti ti-clock-play"></i>
            Collection Observability
          </h1>
          <p className="cr-subtitle">
            Detailed execution history, telemetry, and payload diagnostics across all intelligence sources.
          </p>
        </div>
      </div>

      <div className="cr-layout">
        {/* Main Left Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <i className="ti ti-list-details"></i> Run History
              </div>
              <span className="badge badge-outline" style={{ background: 'rgba(167, 139, 250, 0.1)', borderColor: 'rgba(167, 139, 250, 0.3)', color: '#c4b5fd' }}>{rows.length} records</span>
            </div>
            
            <div className="cr-filter-bar">
              <div className="cr-filter-group">
                <span className="cr-filter-label">Source</span>
                <select className="cr-filter-input" value={filters.source || ''} onChange={(e) => setFilters((f) => ({ ...f, source: e.target.value }))} style={{ width: '160px' }}>
                  <option value="">Any Source</option>
                  {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
              <div className="cr-filter-group">
                <span className="cr-filter-label">Status</span>
                <select className="cr-filter-input" value={filters.status || ''} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))} style={{ width: '160px' }}>
                  <option value="">Any Status</option>
                  {['success', 'warning', 'error'].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>

            <div className="cr-panel-body" style={{ padding: '24px', background: 'rgba(0,0,0,0.15)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {rows.map((r) => <RunCard key={r.run_id || r.id} run={r} />)}
              {!rows.length && <Empty title="No collection runs" sub="Run a collection to populate scan observability." />}
            </div>
          </div>
        </div>

        {/* Sidebar Right Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          
          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <i className="ti ti-chart-bar"></i> Indexed over latest runs
              </div>
            </div>
            <div className="cr-panel-body" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <BarChart data={chartData} />
            </div>
          </div>

          <div className="cr-panel">
            <div className="cr-panel-header">
              <div className="cr-panel-title">
                <i className="ti ti-info-circle"></i> Collector Diagnostics
              </div>
            </div>
            <div className="cr-panel-body" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <p style={{ color: '#a3aab8', fontSize: '13px', lineHeight: 1.6, marginBottom: '16px' }}>
                If <strong>collected &gt; 0</strong> but <strong>indexed = 0</strong>, typical causes are:
              </p>
              <ul style={{ color: '#edf0f5', fontSize: '13px', lineHeight: 1.6, paddingLeft: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <li>Duplicate detection hashes (already known).</li>
                <li>Skipped noise entries (filtered by detection policy).</li>
                <li>Skipped informational items.</li>
                <li>Collector errors (API rate limits, timeouts).</li>
              </ul>
              <p style={{ color: '#a3aab8', fontSize: '13px', lineHeight: 1.6, marginTop: '16px', fontStyle: 'italic' }}>
                Expand each run in the left panel to inspect its persisted payload and error logs.
              </p>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}