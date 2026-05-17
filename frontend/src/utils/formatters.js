import { SOURCE_LABELS } from './constants.js';

export function sourceLabel(value) {
  return SOURCE_LABELS[value] || value || 'unknown';
}

export function formatNumber(value) {
  const number = Number(value || 0);
  return new Intl.NumberFormat().format(number);
}

export function formatDate(value) {
  if (!value || value === 'unknown') return 'unknown';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

export function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

export function compactJson(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return '{}';
  }
}

export function truncate(value, length = 120) {
  const text = String(value || '');
  return text.length > length ? `${text.slice(0, length - 1)}...` : text;
}
