import { useEffect } from 'react';
import { REFRESH_INTERVAL_MS } from '../utils/constants.js';

export function useAutoRefresh(callback, { enabled = true, intervalMs = REFRESH_INTERVAL_MS } = {}) {
  useEffect(() => {
    if (!enabled) return undefined;
    const timer = window.setInterval(callback, intervalMs);
    return () => window.clearInterval(timer);
  }, [callback, enabled, intervalMs]);
}
