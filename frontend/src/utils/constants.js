export const SOURCES = [
  { value: 'github', label: 'GitHub' },
  { value: 'google_alerts', label: 'Google Alerts' },
  { value: 'telegram', label: 'Telegram' }
];

export const SEVERITIES = ['high', 'medium', 'low', 'informational', 'unknown'];
export const CONFIDENCES = ['high', 'medium', 'low', 'unknown'];
export const STATUSES = ['new', 'reviewed', 'false_positive', 'escalated', 'confirmed', 'ignored'];

export const SOURCE_LABELS = {
  github: 'GitHub',
  google_alerts: 'Google Alerts',
  telegram: 'Telegram',
  mock_paste: 'Mock Paste'
};

export const REFRESH_INTERVAL_MS = 60000;
