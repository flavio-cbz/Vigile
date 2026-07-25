import { create } from 'zustand';
import { api } from '../hooks/useApi';
import type { InsightItem } from './uiStore';

interface InsightsState {
  insightsByNode: Record<string, InsightItem[]>;
  loadingByNode: Record<string, boolean>;
  fetchInsights: (nodeId: string) => Promise<void>;
  invalidate: (nodeId: string) => void;
}

export const useInsightsStore = create<InsightsState>((set) => ({
  insightsByNode: {},
  loadingByNode: {},
  fetchInsights: async (nodeId) => {
    if (!nodeId || nodeId === 'all') return;
    set((state) => ({
      loadingByNode: { ...state.loadingByNode, [nodeId]: true },
    }));
    try {
      const data = await api<{ insights: InsightItem[] }>(`/api/nodes/${nodeId}/insights`);
      if (data && data.insights) {
        set((state) => ({
          insightsByNode: { ...state.insightsByNode, [nodeId]: data.insights },
        }));
      }
    } catch (err) {
      console.error(`Failed to fetch insights for node ${nodeId}:`, err);
    } finally {
      set((state) => ({
        loadingByNode: { ...state.loadingByNode, [nodeId]: false },
      }));
    }
  },
  invalidate: (nodeId) => {
    set((state) => {
      const copy = { ...state.insightsByNode };
      delete copy[nodeId];
      return { insightsByNode: copy };
    });
  },
}));
export type { InsightItem };
