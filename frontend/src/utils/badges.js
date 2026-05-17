export function sourceTone(source) {
  if (source === 'github') return 'source-github';
  if (source === 'google_alerts') return 'source-google';
  if (source === 'telegram') return 'source-telegram';
  return 'source-default';
}

export function severityTone(severity) {
  if (severity === 'critical' || severity === 'high') return 'severity-high';
  if (severity === 'medium') return 'severity-medium';
  if (severity === 'low') return 'severity-low';
  return 'severity-unknown';
}

export function statusTone(status) {
  if (status === 'confirmed' || status === 'escalated') return 'status-hot';
  if (status === 'false_positive' || status === 'ignored') return 'status-muted';
  if (status === 'reviewed') return 'status-reviewed';
  return 'status-new';
}
