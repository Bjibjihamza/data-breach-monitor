import { useCallback, useEffect, useMemo, useState } from 'react';
import { getDetections } from '../api/detections.js';
import { cleanFilters } from '../utils/filters.js';

function normalizePage(payload = {}) {
  const items = payload.items || payload.detections || [];
  const limit = Number(payload.limit || 100);
  const offset = Number(payload.offset || 0);
  const total = Number(payload.total || 0);
  return {
    ...payload,
    items,
    detections: items,
    limit,
    offset,
    total,
    has_more: Boolean(payload.has_more ?? offset + items.length < total),
  };
}

function appendUnique(existing = [], next = []) {
  const seen = new Set(existing.map((item) => item.detection_hash || `${item.source}-${item.source_url || item.title || item.processed_at}`));
  const merged = [...existing];
  next.forEach((item) => {
    const key = item.detection_hash || `${item.source}-${item.source_url || item.title || item.processed_at}`;
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(item);
    }
  });
  return merged;
}

export function useDetections(filters = {}, refreshKey) {
  const params = useMemo(() => cleanFilters({ limit: 100, ...filters, offset: 0 }), [JSON.stringify(filters)]);
  const paramsKey = useMemo(() => JSON.stringify(params), [params]);
  const [state, setState] = useState({ data: null, error: null, loading: true, loadingMore: false });

  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, loadingMore: false, error: null }));
    getDetections(params)
      .then((payload) => {
        if (active) setState({ data: normalizePage(payload), error: null, loading: false, loadingMore: false });
      })
      .catch((error) => {
        if (active) setState({ data: null, error, loading: false, loadingMore: false });
      });
    return () => {
      active = false;
    };
  }, [paramsKey, refreshKey]);

  const loadMore = useCallback(async () => {
    if (state.loading || state.loadingMore || !state.data?.has_more) return;
    const nextOffset = Number(state.data.offset || 0) + Number(state.data.limit || params.limit || 100);
    setState((current) => ({ ...current, loadingMore: true, error: null }));
    try {
      const page = normalizePage(await getDetections({ ...params, offset: nextOffset }));
      setState((current) => {
        const currentData = current.data || normalizePage();
        const merged = appendUnique(currentData.detections || [], page.detections || []);
        return {
          data: {
            ...page,
            items: merged,
            detections: merged,
            offset: page.offset,
            has_more: merged.length < page.total,
          },
          error: null,
          loading: false,
          loadingMore: false,
        };
      });
    } catch (error) {
      setState((current) => ({ ...current, error, loadingMore: false }));
    }
  }, [paramsKey, state.data, state.loading, state.loadingMore]);

  return { ...state, loadMore };
}
