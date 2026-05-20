import { useState } from 'react';
import { runSource } from '../../api/scans.js';
import { useScanStatusContext } from '../../context/ScanStatusContext.jsx';
import { SOURCE_META, isActiveStatus } from './scanUi.js';

export default function SourceRunButton({ source, mode = 'incremental', onStarted, className = '' }) {
  const meta = SOURCE_META[source];
  const { refresh, isSourceRunning, sourceStatus } = useScanStatusContext();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const live = sourceStatus(source);
  const status = live.status;
  const running = isSourceRunning(source) || busy;

  const handleClick = async () => {
    setBusy(true);
    setNotice('');
    try {
      const result = await runSource(source, mode);
      if (result?.success === false) {
        setNotice(result.message || 'Scan already running');
      } else {
        setNotice('Scan queued');
        onStarted?.(result);
      }
      await refresh();
    } catch (error) {
      setNotice(error.message || 'Failed to start scan');
    } finally {
      setBusy(false);
    }
  };

  let label = meta?.runLabel || 'Run Scan';
  if (running) label = meta?.runningLabel || 'Running…';
  else if (status === 'failed' || status === 'stale') label = `Retry ${meta?.label || ''} Scan`.trim();
  else if (status === 'success' || status === 'warning') label = meta?.runLabel || 'Run Scan';

  return (
    <div className={className}>
      <button type="button" className="btn btn-primary" onClick={handleClick} disabled={running}>
        {running ? <i className="ti ti-loader-2 scan-spinner" /> : <i className="ti ti-radar-2" />}
        {label}
      </button>
      {running && live.message && (
        <div className="scan-message" style={{ marginTop: 8 }}>
          {live.phase}: {live.message}
        </div>
      )}
      {notice && <div className="scan-message" style={{ marginTop: 8 }}>{notice}</div>}
    </div>
  );
}
