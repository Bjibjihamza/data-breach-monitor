import { createContext, useContext } from 'react';
import { useScanStatus } from '../hooks/useScanStatus.js';

const ScanStatusContext = createContext(null);

export function ScanStatusProvider({ children, refreshKey, onSettled }) {
  const value = useScanStatus({ pollIntervalMs: 3000, refreshKey, onSettled });
  return <ScanStatusContext.Provider value={value}>{children}</ScanStatusContext.Provider>;
}

export function useScanStatusContext() {
  const ctx = useContext(ScanStatusContext);
  if (!ctx) {
    throw new Error('useScanStatusContext must be used within ScanStatusProvider');
  }
  return ctx;
}
