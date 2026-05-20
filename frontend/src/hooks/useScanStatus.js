import { useCallback, useEffect, useRef, useState } from 'react';
import { getScanStatus } from '../api/scans.js';
import { runAllSources, runSource as runSourceApi } from '../api/scans.js';

const ACTIVE = new Set(['queued', 'running']);

function isActiveStatus(status) {
  return ACTIVE.has(String(status || '').toLowerCase());
}

export function useScanStatus({ pollIntervalMs = 3000, refreshKey = 0, onSettled } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);
  const wasActiveRef = useRef(false);

  const refreshStatus = useCallback(async () => {
    try {
      const payload = await getScanStatus();
      setData(payload);
      setError(null);
      return payload;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    refreshStatus();
  }, [refreshStatus, refreshKey]);

  const anyRunning = Boolean(
    data?.any_running ??
      data?.any_active ??
      Object.values(data?.sources || {}).some((source) => isActiveStatus(source?.status))
  );

  useEffect(() => {
    if (wasActiveRef.current && !anyRunning) {
      onSettled?.();
    }
    wasActiveRef.current = anyRunning;
  }, [anyRunning, onSettled]);

  useEffect(() => {
    if (!anyRunning) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return undefined;
    }
    pollRef.current = setInterval(() => {
      refreshStatus();
    }, pollIntervalMs);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [anyRunning, pollIntervalMs, refreshStatus]);

  const sourceStatus = useCallback(
    (source) => data?.sources?.[source] || { status: 'idle', phase: 'idle' },
    [data]
  );

  const isSourceRunning = useCallback(
    (source) => isActiveStatus(sourceStatus(source).status),
    [sourceStatus]
  );

  const runSource = useCallback(
    async (source, mode = 'incremental') => {
      const result = await runSourceApi(source, mode);
      await refreshStatus();
      return result;
    },
    [refreshStatus]
  );

  const runAll = useCallback(
    async (mode = 'incremental') => {
      const result = await runAllSources(mode);
      await refreshStatus();
      return result;
    },
    [refreshStatus]
  );

  return {
    data,
    loading,
    error,
    refresh: refreshStatus,
    refreshStatus,
    anyActive: anyRunning,
    anyRunning,
    scanGroupId: data?.scan_group_id || null,
    sources: data?.sources || {},
    sourceStatus,
    isSourceRunning,
    runSource,
    runAll,
  };
}
