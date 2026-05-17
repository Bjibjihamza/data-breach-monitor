import { useState } from 'react';
import { scanAll } from '../api/scans.js';

export default function Topbar({ lastRefresh, refresh, autoRefresh, setAutoRefresh }) {
  const ts = lastRefresh ? new Date(lastRefresh).toLocaleTimeString() : '—';
  const [scanAllBusy, setScanAllBusy] = useState(false);

  const handleScanAll = async () => {
    setScanAllBusy(true);
    try {
      await scanAll('incremental');
      refresh?.();
    } catch (e) {
      console.error(e);
    } finally {
      setScanAllBusy(false);
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-search">
          <i className="ti ti-search" />
          <input type="text" placeholder="Search detections, sources, keywords..." />
        </div>
        <span className="topbar-refresh">
          <i className="ti ti-clock" />
          Last sync: {ts}
        </span>
      </div>
      <div className="topbar-actions">
        <label className="toggle-switch" title="Auto-refresh">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          <span className="toggle-slider" />
        </label>
        
        <button className="btn btn-ghost" title="Notifications">
          <i className="ti ti-bell" />
        </button>

        <button className="btn btn-ghost" onClick={refresh} title="Refresh Data">
          <i className="ti ti-refresh" />
        </button>

        <button className="btn btn-primary" onClick={handleScanAll} disabled={scanAllBusy}>
          <i className="ti ti-radar-2" />
          {scanAllBusy ? 'Scanning...' : 'Run Scan'}
        </button>
        
        <button className="btn btn-ghost" style={{ borderRadius: '50%', padding: '4px' }}>
          <i className="ti ti-user-circle" style={{ fontSize: '24px' }} />
        </button>
      </div>
    </header>
  );
}
