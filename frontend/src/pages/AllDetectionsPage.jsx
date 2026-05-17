import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useDetections } from '../hooks/useDetections.js';
import { CONFIDENCES, SEVERITIES, SOURCES, STATUSES } from '../utils/constants.js';
import {
  DetectionDrawer, DetectionCards, ErrorBanner, Loading, fmt
} from './_shared.jsx';

export default function AllDetectionsPage() {
  const { refreshKey, setModalOpen } = useOutletContext();
  const [filters, setFilters] = useState({ limit: 100 });
  const [selected, setSelected] = useState(null);
  const detections = useDetections(filters, refreshKey);

  useEffect(() => {
    setModalOpen(Boolean(selected));
    return () => setModalOpen(false);
  }, [selected, setModalOpen]);

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Detection Center</h1>
          <p className="page-subtitle">Triage, review, and analyze alerts from all sources</p>
        </div>
      </div>

      <ErrorBanner error={detections.error} />

      <div className="filters-bar">
        <div className="filter-group">
          <span className="filter-label">Source</span>
          <select className="filter-select" value={filters.source || ''} onChange={set('source')}>
            <option value="">Any</option>
            {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">Severity</span>
          <select className="filter-select" value={filters.severity || ''} onChange={set('severity')}>
            <option value="">Any</option>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">Confidence</span>
          <select className="filter-select" value={filters.confidence || ''} onChange={set('confidence')}>
            <option value="">Any</option>
            {CONFIDENCES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">Status</span>
          <select className="filter-select" value={filters.status || ''} onChange={set('status')}>
            <option value="">Any</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="filter-group" style={{ flexGrow: 1, justifyContent: 'flex-end' }}>
          <div style={{ position: 'relative' }}>
            <i className="ti ti-search" style={{ position: 'absolute', left: '10px', top: '8px', color: 'var(--text-tertiary)', fontSize: '14px' }} />
            <input 
              className="filter-input" 
              value={filters.search || ''} 
              onChange={set('search')} 
              placeholder="Search detections..." 
              style={{ width: '260px', paddingLeft: '32px' }} 
            />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Active Detections</span>
          <span className="card-subtitle">{fmt(detections.data?.total ?? 0)} total matches</span>
        </div>
        <div className="card-body">
          {detections.loading && <Loading label="Loading detections" />}
          {!detections.loading && (
            <DetectionCards
              detections={detections.data?.detections || []}
              onSelect={setSelected}
            />
          )}
        </div>
      </div>

      <DetectionDrawer detection={selected} onClose={() => setSelected(null)} onUpdated={setSelected} />
    </div>
  );
}
