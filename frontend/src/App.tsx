import { Routes, Route } from 'react-router';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { RootLayout } from './components/layout/RootLayout';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { NodeDetail } from './pages/NodeDetail';
import { Proposals } from './pages/Proposals';
import { Audit } from './pages/Audit';
import { Plugins } from './pages/Plugins';
import { Chat } from './pages/Chat';
import { Settings } from './pages/Settings';
import { Servers } from './pages/Servers';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
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
        <Route path="servers" element={<Servers />} />
        <Route path="proposals" element={<Proposals />} />
        <Route path="audit" element={<Audit />} />
        <Route path="plugins" element={<Plugins />} />
        <Route path="settings" element={<Settings />} />
        <Route path="chat/:id" element={<Chat />} />
        <Route path="chat/new" element={<Chat />} />
      </Route>
    </Routes>
  );
}
