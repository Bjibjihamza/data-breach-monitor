import { useCallback, useMemo } from 'react';
import { getDetections } from '../api/detections.js';
import { cleanFilters } from '../utils/filters.js';
import { useResource } from './useResource.js';

export function useDetections(filters = {}, refreshKey) {
  const params = useMemo(() => cleanFilters({ limit: 100, ...filters }), [JSON.stringify(filters)]);
  const loader = useCallback(() => getDetections(params), [JSON.stringify(params), refreshKey]);
  return useResource(loader, [params, refreshKey]);
}
