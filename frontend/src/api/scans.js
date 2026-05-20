import { ApiError, getJson, postJson, request } from './client.js';

const withMode = (path, mode) => (mode ? `${path}?mode=${encodeURIComponent(mode)}` : path);

export const getScanStatus = () => getJson('/scan/status');
export const getSourceScanStatus = (source) =>
  getJson(`/scan/status/${String(source).replace(/-/g, '_')}`);

export const scanGitHub = (mode = 'incremental') => postJson(withMode('/scan/github', mode));
export const scanGoogleAlerts = (mode = 'incremental') => postJson(withMode('/scan/google-alerts', mode));
export const scanTelegram = (mode = 'incremental') => postJson(withMode('/scan/telegram', mode));
export const scanAllSources = (mode = 'incremental') => postJson(withMode('/scan/all', mode));

const SOURCE_RUNNERS = {
  github: scanGitHub,
  google_alerts: scanGoogleAlerts,
  telegram: scanTelegram,
};

export async function runSource(source, mode = 'incremental') {
  const runner = SOURCE_RUNNERS[source];
  if (!runner) {
    throw new ApiError(`Unsupported source: ${source}`);
  }
  try {
    return await runner(mode);
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      const detail = error.payload?.detail || error.payload;
      if (detail && typeof detail === 'object') {
        return { success: false, ...detail };
      }
    }
    throw error;
  }
}

export async function runAllSources(mode = 'incremental') {
  return scanAllSources(mode);
}

/** @deprecated use runAllSources */
export async function scanAll(mode = 'incremental') {
  const payload = await runAllSources(mode);
  const results = payload?.results || {};
  return ['github', 'google_alerts', 'telegram'].map((source) => ({
    source,
    ok: Boolean(results[source]?.success),
    result: results[source] || null,
    error: results[source]?.success === false ? results[source]?.message || 'already running' : '',
  }));
}

export const getInitialBackfillStatus = () => request('/admin/initial-backfill');
export const triggerInitialBackfill = () => postJson('/admin/initial-backfill/run');
