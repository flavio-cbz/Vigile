import { Routes, Route, Navigate } from 'react-router';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { RootLayout } from './components/layout/RootLayout';
import { LoginPage } from './pages/LoginPage';
import { Dashboard } from './pages/Dashboard';
import { NodeDetail } from './pages/NodeDetail';
import { ProposalsPage } from './pages/ProposalsPage';
import { SettingsPage } from './pages/SettingsPage';
import { ServersPage } from './pages/ServersPage';
import { PluginsPage } from './pages/PluginsPage';
import { AutomationsPage } from './pages/AutomationsPage';

import { useTheme } from './hooks/useTheme';
import { useUiStore } from './store/uiStore';
import { useEffect } from 'react';

const ChatRedirect = () => {
  const openCopilot = useUiStore((s) => s.openCopilot);
  useEffect(() => {
    openCopilot({ trigger: 'manual' });
  }, [openCopilot]);
  return <Navigate to="/" replace />;
};

export default function App() {
  useTheme();

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <RootLayout />
          </ProtectedRoute>
        }
      >

        <Route index element={<Dashboard />} />
        <Route path="nodes/:id" element={<NodeDetail />} />
        <Route path="proposals" element={<ProposalsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="plugins" element={<PluginsPage />} />
        <Route path="automations" element={<AutomationsPage />} />
        <Route path="chat/new" element={<ChatRedirect />} />
      </Route>

      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  );
}
