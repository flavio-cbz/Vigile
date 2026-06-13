import { create } from 'zustand';


interface LayoutState {
  isCopilotOpen: boolean;
  isSidebarOpen: boolean;
  isSidebarCollapsed: boolean;
  isAddNodeModalOpen: boolean;
  pendingCount: number;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  setCopilotOpen: (open: boolean) => void;
  toggleCopilot: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  toggleSidebarCollapse: () => void;
  setAddNodeModalOpen: (open: boolean) => void;
  setPendingCount: (count: number) => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  isCopilotOpen: false,
  isSidebarOpen: false,
  isSidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true',
  isAddNodeModalOpen: false,
  pendingCount: 0,
  paletteOpen: false,
  setPaletteOpen: (open) => set({ paletteOpen: open }),
  setCopilotOpen: (open) => set({ isCopilotOpen: open }),
  toggleCopilot: () => set((state) => ({ isCopilotOpen: !state.isCopilotOpen })),
  setSidebarOpen: (open) => set({ isSidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  toggleSidebarCollapse: () =>
    set((state) => {
      const next = !state.isSidebarCollapsed;
      localStorage.setItem('sidebarCollapsed', String(next));
      return { isSidebarCollapsed: next };
    }),
  setAddNodeModalOpen: (open) => set({ isAddNodeModalOpen: open }),
  setPendingCount: (count) => set({ pendingCount: count }),
}));

