import { useCallback } from 'react';
import { getSummary } from '../api/analytics.js';
import { useResource } from './useResource.js';

export function useSummary(refreshKey) {
  const loader = useCallback(() => getSummary(), [refreshKey]);
  return useResource(loader, [refreshKey]);
}
