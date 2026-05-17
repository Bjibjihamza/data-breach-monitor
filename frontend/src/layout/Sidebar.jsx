import { NavLink } from 'react-router-dom';

const NAV = [
  { group: 'Intelligence', items: [
    { to: '/', label: 'Overview', icon: 'ti-layout-dashboard', end: true },
    { to: '/detections', label: 'Detection Center', icon: 'ti-shield-search' },
    { to: '/correlations', label: 'Correlations', icon: 'ti-affiliate' },
    { to: '/intelligence', label: 'Intelligence', icon: 'ti-report-analytics' },
  ]},
  { group: 'Sources', items: [
    { to: '/github', label: 'GitHub', icon: 'ti-brand-github' },
    { to: '/google-alerts', label: 'Google Alerts', icon: 'ti-rss' },
    { to: '/telegram', label: 'Telegram', icon: 'ti-brand-telegram' },
  ]},
  { group: 'Observability', items: [
    { to: '/runs', label: 'Collection Runs', icon: 'ti-activity' },
    { to: '/state', label: 'Collection State', icon: 'ti-database' },
    { to: '/diagnostics', label: 'Diagnostics', icon: 'ti-list-details' },
    { to: '/settings', label: 'Settings', icon: 'ti-settings' },
  ]},
];

export default function Sidebar({ expanded, setExpanded }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-brand-dot" />
        {expanded && 'DBM SOC'}
      </div>
      <nav className="sidebar-nav">
        {NAV.map(({ group, items }) => (
          <div key={group}>
            <div className="sidebar-section">{group}</div>
            {items.map(({ to, label, icon, end }) => (
              <NavLink 
                key={to} 
                to={to} 
                end={end} 
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                data-tooltip={!expanded ? label : undefined}
              >
                <i className={`ti ${icon} nav-icon`} aria-hidden="true" />
                <span className="nav-label">{label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div 
        className="sidebar-toggle" 
        onClick={() => setExpanded(!expanded)}
        title={expanded ? "Collapse sidebar" : "Expand sidebar"}
      >
        <i className={`ti ti-chevron-${expanded ? 'left' : 'right'}`} />
      </div>
    </aside>
  );
}
