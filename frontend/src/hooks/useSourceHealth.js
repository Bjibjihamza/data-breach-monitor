import { useCallback } from 'react';
import { getSourceHealth } from '../api/analytics.js';
import { useResource } from './useResource.js';

export function useSourceHealth(refreshKey) {
  const loader = useCallback(() => getSourceHealth(), [refreshKey]);
  return useResource(loader, [refreshKey]);
}
