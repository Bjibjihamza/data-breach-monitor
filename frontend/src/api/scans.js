import { postJson, request } from './client.js';

const withMode = (path, mode) => (mode ? `${path}?mode=${encodeURIComponent(mode)}` : path);

export const scanGitHub = (mode = 'incremental') => postJson(withMode('/scan/github', mode));
export const scanGoogleAlerts = (mode = 'incremental') => postJson(withMode('/scan/google-alerts', mode));
export const scanTelegram = (mode = 'incremental') => postJson(withMode('/scan/telegram', mode));
export const scanAllSources = (mode = 'incremental') => postJson(withMode('/scan/all', mode));

export async function scanAll(mode = 'incremental') {
  try {
    const payload = await scanAllSources(mode);
    return [
      { source: 'github', ok: true, result: payload?.results?.github || null, error: '' },
      { source: 'google_alerts', ok: true, result: payload?.results?.google_alerts || null, error: '' },
      { source: 'telegram', ok: true, result: payload?.results?.telegram || null, error: '' },
    ];
  } catch (firstError) {
    const tasks = await Promise.allSettled([
      scanGitHub(mode),
      scanGoogleAlerts(mode),
      scanTelegram(mode),
    ]);
    return tasks.map((task, index) => ({
      source: ['github', 'google_alerts', 'telegram'][index],
      ok: task.status === 'fulfilled',
      result: task.status === 'fulfilled' ? task.value : null,
      error: task.status === 'rejected' ? task.reason?.message || firstError?.message || 'Scan failed' : '',
    }));
  }
}

export const getInitialBackfillStatus = () => request('/admin/initial-backfill');
export const triggerInitialBackfill = () => postJson('/admin/initial-backfill/run');
