import { lazy, Suspense, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { RootLayout } from './components/layout/RootLayout';
import { LoginPage } from './pages/LoginPage';
import { PluginRouter } from './plugins/PluginRouter';
import { useTheme } from './hooks/useTheme';
import { useUiStore } from './store/uiStore';

const Dashboard = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })));
const NodeDetail = lazy(() => import('./pages/NodeDetail').then((m) => ({ default: m.NodeDetail })));
const ProposalsPage = lazy(() => import('./pages/ProposalsPage').then((m) => ({ default: m.ProposalsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));
const ServersPage = lazy(() => import('./pages/ServersPage').then((m) => ({ default: m.ServersPage })));
const PluginsPage = lazy(() => import('./pages/PluginsPage').then((m) => ({ default: m.PluginsPage })));
const EventDetailPage = lazy(() => import('./pages/EventDetailPage').then((m) => ({ default: m.EventDetailPage })));
const RouteLoadingFallback = () => (
  <div className="flex items-center justify-center min-h-[400px] w-full">
    <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
  </div>
);

const ChatRedirect = () => {
  const openCopilot = useUiStore((s) => s.openCopilot);
  const navigate = useNavigate();

  useEffect(() => {
    openCopilot({ trigger: 'manual' });
    navigate('/', { replace: true });
  }, [openCopilot, navigate]);

  return null;
};

export default function App() {
  useTheme();

  return (
    <Suspense fallback={<RouteLoadingFallback />}>
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
          <Route path="plugins/*" element={<PluginRouter />} />
          <Route path="events/:alertId" element={<EventDetailPage />} />
          <Route path="chat" element={<ChatRedirect />} />
          <Route path="chat/new" element={<ChatRedirect />} />
        </Route>

        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Suspense>
  );
}
