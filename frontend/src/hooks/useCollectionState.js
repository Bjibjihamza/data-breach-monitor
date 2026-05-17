import { useCallback } from 'react';
import { getCollectionState } from '../api/debug.js';
import { useResource } from './useResource.js';

export function useCollectionState(refreshKey) {
  const loader = useCallback(() => getCollectionState(), [refreshKey]);
  return useResource(loader, [refreshKey]);
}
