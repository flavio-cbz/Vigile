import React from 'react';
import { Outlet } from 'react-router';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { CopilotPanel } from '../copilot/CopilotPanel';
import { ToastContainer } from '../ui/ToastContainer';
import { CommandPalette } from '../ui/CommandPalette';
import { AddNodeModal } from '../modals/AddNodeModal';
import { useLayoutStore } from '../../store/layoutStore';
import { useAuthStore } from '../../store/authStore';
import { api } from '../../hooks/useApi';
import { usePolling } from '../../hooks/usePolling';

export const RootLayout: React.FC = () => {
  const { isAddNodeModalOpen, setAddNodeModalOpen } = useLayoutStore();

  const fetchPendingCount = async () => {
    const token = useAuthStore.getState().accessToken;
    if (!token) return;
    try {
      const data = await api<any[]>('/api/chat/proposals?status=PENDING', { skipToast: true });
      if (data) {
        useLayoutStore.getState().setPendingCount(data.length);
      }
    } catch {
      // Swallow — polling errors are non-critical
    }
  };

  usePolling('pending_proposals_count_poll', fetchPendingCount, 60000);

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-row bg-bg text-ink relative">
      <Sidebar />

      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">
        <TopBar />

        <main className="flex-1 overflow-y-auto overflow-x-hidden p-6 relative bg-gradient-to-b from-bg to-bg-alt">
          <Outlet />
        </main>
      </div>

      <CopilotPanel />
      <ToastContainer />
      <CommandPalette />

      {isAddNodeModalOpen && (
        <AddNodeModal onClose={() => setAddNodeModalOpen(false)} />
      )}
    </div>
  );
};
