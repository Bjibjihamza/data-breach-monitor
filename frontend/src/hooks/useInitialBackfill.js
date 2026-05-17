import { useCallback } from 'react';
import { getInitialBackfillStatus } from '../api/scans.js';
import { useResource } from './useResource.js';

export function useInitialBackfill(refreshKey) {
  const loader = useCallback(() => getInitialBackfillStatus(), [refreshKey]);
  return useResource(loader, [refreshKey]);
}
