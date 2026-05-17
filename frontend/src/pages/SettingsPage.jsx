import { useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { getGitHubConfig, getGoogleAlertsConfig, getHealth, getTelegramConfig } from '../api/debug.js';
import { useResource } from '../hooks/useResource.js';
import { ErrorBanner, JsonBlock, fmt } from './_shared.jsx';

export default function SettingsPage() {
  const { refreshKey } = useOutletContext();

  const loader = useCallback(async () => {
    const [health, github, google, telegram] = await Promise.allSettled([
      getHealth(), getGitHubConfig(), getGoogleAlertsConfig(), getTelegramConfig()
    ]);
    return { health, github, google, telegram };
  }, [refreshKey]);

  const result = useResource(loader, [refreshKey]);
  const d = result.data || {};

  const kpis = [
    ['API Health',        d.health?.status === 'fulfilled' ? d.health.value.status : 'unknown', d.health?.status === 'fulfilled' ? 'success' : 'critical'],
    ['GitHub Token',      d.github?.status === 'fulfilled' && d.github.value.github_token_present ? 'Present' : 'Absent', d.github?.status === 'fulfilled' && d.github.value.github_token_present ? 'success' : 'critical'],
    ['Google Feeds',      d.google?.status === 'fulfilled' ? fmt(d.google.value.valid_feeds_count ?? 0) : '—', 'info'],
    ['Telegram Channels', d.telegram?.status === 'fulfilled' ? fmt(d.telegram.value.enabled_channels_count ?? d.telegram.value.channels_count ?? 0) : '—', 'info'],
  ];

  const panels = [
    ['GitHub global policy', d.github,   ['max_queries_per_run', 'max_file_fetches', 'max_pages_per_query', 'max_results_per_query', 'total_query_specs', 'global_policy', 'organization_watchlists']],
    ['Google Alerts limits', d.google,  null],
    ['Telegram channels',   d.telegram, null],
  ];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Platform Settings</h1>
          <p className="page-subtitle">Read-only configuration and connection statuses</p>
        </div>
      </div>

      <ErrorBanner error={result.error} />

      <div className="hero-metrics">
        {kpis.map(([label, value, status]) => (
          <div className="metric-card" key={label}>
            <div className="metric-header">
              {label}
              <div className={`metric-icon ${status}`}><i className={status === 'success' ? 'ti ti-check' : status === 'critical' ? 'ti ti-x' : 'ti ti-info-circle'} /></div>
            </div>
            <div className="metric-value" style={{ fontSize: '24px' }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="grid-3">
        {panels.map(([title, result, pick]) => {
          const ok = result?.status === 'fulfilled';
          const raw = ok ? (pick ? Object.fromEntries(pick.map((k) => [k, result.value[k]])) : result.value) : { error: result?.reason?.message || 'unavailable' };
          return (
            <div className="card" key={title}>
              <div className="card-header"><span className="card-title">{title}</span></div>
              <div className="card-body" style={{ padding: '16px' }}><JsonBlock data={raw} /></div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
