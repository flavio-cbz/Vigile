import { create } from 'zustand';
import { themes, type ThemeKey } from '../design/themes';

export interface InsightItem {
  type: string;
  severity: 'ok' | 'warning' | 'critical' | 'offline' | 'info';
  icon: string;
  headline: string;
  detail: string;
  raw?: any;
}

export interface ActionProposal {
  id: string;
  node_id: string;
  action: string;
  target: string;
  params?: Record<string, any>;
  reasoning: string;
  risk_level: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED';
  created_by?: string;
  created_at: number;
  updated_at?: number;
  executed_at?: number | null;
  approved_by?: string | null;
  rejected_by?: string | null;
  rejection_reason?: string | null;
}

export type CopilotContext = {
  trigger: 'proposal' | 'insight' | 'diagnostic' | 'manual';
  node_id?: string;
  insight?: InsightItem;
  proposal?: ActionProposal;
};

interface UIState {
  theme: ThemeKey;
  setTheme: (t: ThemeKey) => void;

  copilotOpen: boolean;
  copilotContext: CopilotContext | null;
  openCopilot: (ctx: CopilotContext) => void;
  closeCopilot: () => void;

  activeNodeId: string | null;
  setActiveNode: (id: string | null) => void;
}

const getInitialTheme = (): ThemeKey => {
  const saved = localStorage.getItem('vigile_theme');
  if (saved && saved in themes) {
    return saved as ThemeKey;
  }
  const themeMap: Record<string, ThemeKey> = {
    'cold-night': 'cool-dark',
    'operator-gray': 'gray-dark',
    'light-ops': 'light'
  };
  if (saved && saved in themeMap) {
    const mapped = themeMap[saved];
    localStorage.setItem('vigile_theme', mapped);
    return mapped;
  }
  return 'warm-dark';
};

export const useUiStore = create<UIState>((set) => ({
  theme: getInitialTheme(),
  setTheme: (theme) => {
    localStorage.setItem('vigile_theme', theme);
    set({ theme });
  },

  copilotOpen: false,
  copilotContext: null,
  openCopilot: (copilotContext) => set({ copilotOpen: true, copilotContext }),
  closeCopilot: () => set({ copilotOpen: false, copilotContext: null }),

  activeNodeId: 'all',
  setActiveNode: (activeNodeId) => set({ activeNodeId }),
}));
export type { ThemeKey };
