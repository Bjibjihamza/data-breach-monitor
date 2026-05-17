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
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Collection Runs</h1>
          <p className="page-subtitle">Scan observability, indexed items, and collector diagnostics</p>
        </div>
      </div>

      <ErrorBanner error={runs.error} />

      <div className="filters-bar">
        <div className="filter-group">
          <span className="filter-label">Source</span>
          <select className="filter-select" value={filters.source || ''} onChange={(e) => setFilters((f) => ({ ...f, source: e.target.value }))}>
            <option value="">Any</option>
            {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <span className="filter-label">Status</span>
          <select className="filter-select" value={filters.status || ''} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
            <option value="">Any</option>
            {['success', 'warning', 'error'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><span className="card-title">Indexed over latest runs</span></div>
          <div className="card-body"><BarChart data={chartData} /></div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Collector Diagnostics</span></div>
          <div className="card-body">
            <p style={{ color: 'var(--text-tertiary)', fontSize: 13, lineHeight: 1.7 }}>
              If collected &gt; 0 but indexed = 0, typical causes are duplicate detection hashes, skipped noise entries,
              skipped informational items, or collector errors. Expand each run below to inspect its persisted payload.
            </p>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {rows.map((r) => <RunCard key={r.run_id || r.id} run={r} />)}
        {!rows.length && <Empty title="No collection runs" sub="Run a collection to populate scan observability." />}
      </div>
    </div>
  );
}