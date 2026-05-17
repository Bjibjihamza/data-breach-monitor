import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar.jsx';
import Topbar from './Topbar.jsx';

export default function DashboardLayout({ context }) {
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

  return (
    <div className={`shell ${sidebarExpanded ? 'sidebar-expanded' : ''}`}>
      <Sidebar expanded={sidebarExpanded} setExpanded={setSidebarExpanded} />
      <div className="main">
        <Topbar {...context} />
        <main className="page-scroll">
          <Outlet context={context} />
        </main>
      </div>
    </div>
  );
}