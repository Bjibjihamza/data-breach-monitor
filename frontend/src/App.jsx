import { useCallback, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import DashboardLayout from './layout/DashboardLayout.jsx';
import AllDetectionsPage from './pages/AllDetectionsPage.jsx';
import CollectionRunsPage from './pages/CollectionRunsPage.jsx';
import CollectionStatePage from './pages/CollectionStatePage.jsx';
import CorrelationsPage from './pages/CorrelationsPage.jsx';
import GitHubPage from './pages/GitHubPage.jsx';
import GoogleAlertsPage from './pages/GoogleAlertsPage.jsx';
import IntelligencePage from './pages/IntelligencePage.jsx';
import OverviewPage from './pages/OverviewPage.jsx';
import SettingsPage from './pages/SettingsPage.jsx';
import SourceDiagnosticsPage from './pages/SourceDiagnosticsPage.jsx';
import TelegramPage from './pages/TelegramPage.jsx';
import { useAutoRefresh } from './hooks/useAutoRefresh.js';

export default function App() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const refresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
    setLastRefresh(new Date());
  }, []);

  useAutoRefresh(autoRefresh && !modalOpen, refresh, 30000);

  const context = { refreshKey, lastRefresh, refresh, autoRefresh, setAutoRefresh, modalOpen, setModalOpen };

  return (
    <BrowserRouter basename="/dashboard/" future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route element={<DashboardLayout context={context} />}>
          <Route index element={<OverviewPage />} />
          <Route path="detections" element={<AllDetectionsPage />} />
          <Route path="correlations" element={<CorrelationsPage />} />
          <Route path="intelligence" element={<IntelligencePage />} />
          <Route path="github" element={<GitHubPage />} />
          <Route path="google-alerts" element={<GoogleAlertsPage />} />
          <Route path="telegram" element={<TelegramPage />} />
          <Route path="runs" element={<CollectionRunsPage />} />
          <Route path="state" element={<CollectionStatePage />} />
          <Route path="diagnostics" element={<SourceDiagnosticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
