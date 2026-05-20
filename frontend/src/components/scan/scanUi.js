export const SOURCE_META = {
  github: {
    key: 'github',
    label: 'GitHub',
    title: 'GitHub Intelligence',
    icon: 'ti-brand-github',
    accent: '#60a5fa',
    runLabel: 'Run GitHub Scan',
    runningLabel: 'GitHub Running…',
  },
  google_alerts: {
    key: 'google_alerts',
    label: 'News Intelligence',
    title: 'News Intelligence',
    icon: 'ti-rss',
    accent: '#f59e0b',
    runLabel: 'Run News Scan',
    runningLabel: 'News Scan Running…',
  },
  telegram: {
    key: 'telegram',
    label: 'Telegram',
    title: 'Telegram Intelligence',
    icon: 'ti-brand-telegram',
    accent: '#38bdf8',
    runLabel: 'Run Telegram Scan',
    runningLabel: 'Telegram Running…',
  },
};

export function statusTone(status) {
  const value = String(status || 'idle').toLowerCase();
  if (value === 'success' || value === 'completed') return 'ok';
  if (value === 'running' || value === 'queued') return 'run';
  if (value === 'failed' || value === 'error' || value === 'stale') return 'err';
  if (value === 'warning' || value === 'already_running') return 'warn';
  return 'idle';
}

export function isActiveStatus(status) {
  const value = String(status || '').toLowerCase();
  return value === 'queued' || value === 'running';
}

export function shortenId(value, length = 10) {
  if (!value) return '—';
  const text = String(value);
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

export function progressPercent(source) {
  const progress = source?.progress || {};
  const total = Number(progress.configured_items || progress.queries_total || progress.feeds_total || progress.channels_total || 0);
  const done = Number(progress.processed_items || progress.queries_processed || progress.feeds_processed || progress.channels_processed || 0);
  if (!total) return null;
  return Math.min(100, Math.round((done / total) * 100));
}
