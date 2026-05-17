import { useCallback, useMemo } from 'react';
import { getCollectionRuns } from '../api/analytics.js';
import { cleanFilters } from '../utils/filters.js';
import { useResource } from './useResource.js';

export function useCollectionRuns(filters = {}, refreshKey) {
  const params = useMemo(() => cleanFilters({ limit: 50, ...filters }), [JSON.stringify(filters)]);
  const loader = useCallback(() => getCollectionRuns(params), [JSON.stringify(params), refreshKey]);
  return useResource(loader, [params, refreshKey]);
}
