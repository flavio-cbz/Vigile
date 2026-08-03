import { create } from 'zustand';
import { api } from '../hooks/useApi';
import type { InsightItem } from './uiStore';
import type { InsightsMeta } from '../components/node-detail/types';

interface InsightsState {
  insightsByNode: Record<string, InsightItem[]>;
  metaByNode: Record<string, InsightsMeta>;
  loadingByNode: Record<string, boolean>;
  fetchInsights: (nodeId: string) => Promise<void>;
  invalidate: (nodeId: string) => void;
}

export const useInsightsStore = create<InsightsState>((set) => ({
  insightsByNode: {},
  metaByNode: {},
  loadingByNode: {},
  fetchInsights: async (nodeId) => {
    if (!nodeId || nodeId === 'all') return;
    set((state) => ({
      loadingByNode: { ...state.loadingByNode, [nodeId]: true },
    }));
    try {
      const data = await api<{
        insights: InsightItem[];
        data_window_hours?: number;
        observation_ready?: boolean;
        profile_confidence?: 'none' | 'low' | 'medium' | 'high';
        next_profile_refresh_at?: string | null;
        profile_generated_at?: string | null;
        per_type_readiness?: InsightsMeta['per_type_readiness'];
      }>(`/api/nodes/${nodeId}/insights`);
      if (data && data.insights) {
        set((state) => ({
          insightsByNode: { ...state.insightsByNode, [nodeId]: data.insights },
          metaByNode: {
            ...state.metaByNode,
            [nodeId]: {
              data_window_hours: data.data_window_hours ?? 0,
              observation_ready: data.observation_ready ?? true,
              profile_confidence: data.profile_confidence ?? 'high',
              next_profile_refresh_at: data.next_profile_refresh_at ?? null,
              profile_generated_at: data.profile_generated_at ?? null,
              per_type_readiness: data.per_type_readiness,
            },
          },
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
      const insightsCopy = { ...state.insightsByNode };
      const metaCopy = { ...state.metaByNode };
      delete insightsCopy[nodeId];
      delete metaCopy[nodeId];
      return { insightsByNode: insightsCopy, metaByNode: metaCopy };
    });
  },
}));
export type { InsightItem };
