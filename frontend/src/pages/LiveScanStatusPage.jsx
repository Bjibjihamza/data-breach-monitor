import { useOutletContext } from 'react-router-dom';
import LiveScanStatusCards from '../components/scan/LiveScanStatusCards.jsx';
import SourceRunButton from '../components/scan/SourceRunButton.jsx';
import { useScanStatusContext } from '../context/ScanStatusContext.jsx';
import { runAllSources } from '../api/scans.js';
import { ErrorBanner } from './_shared.jsx';
import { useState } from 'react';

export default function LiveScanStatusPage() {
  const { refresh } = useOutletContext();
  const { refresh: refreshStatus, anyActive, error } = useScanStatusContext();
  const [busy, setBusy] = useState(false);

  const handleRunAll = async () => {
    setBusy(true);
    try {
      await runAllSources('incremental');
      await refreshStatus();
      refresh?.();
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  };

  const handleRefresh = async () => {
    await refreshStatus();
    refresh?.();
  };

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, color: '#fff', fontSize: 28 }}>Live Scan Status</h1>
          <p style={{ margin: '8px 0 0', color: '#94a3b8' }}>
            Real-time progress for GitHub, News Intelligence, and Telegram collectors.
          </p>
        </div>
        <div className="scan-actions">
          <button type="button" className="btn btn-ghost" onClick={handleRefresh}>
            <i className="ti ti-refresh" /> Refresh Status
          </button>
          <button type="button" className="btn btn-primary" onClick={handleRunAll} disabled={busy || anyActive}>
            <i className="ti ti-radar-2" />
            {busy ? 'Starting…' : anyActive ? 'Scan In Progress' : 'Run All Sources'}
          </button>
        </div>
      </div>
      <ErrorBanner error={error} />
      <LiveScanStatusCards />
      <div className="scan-panel">
        <div className="scan-panel-title" style={{ marginBottom: 12 }}>Per-source controls</div>
        <div className="scan-actions">
          <SourceRunButton source="github" onStarted={() => refresh?.()} />
          <SourceRunButton source="google_alerts" onStarted={() => refresh?.()} />
          <SourceRunButton source="telegram" onStarted={() => refresh?.()} />
        </div>
      </div>
    </div>
  );
}
