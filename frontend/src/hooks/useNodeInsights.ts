import { useEffect, useCallback } from 'react';
import { useInsightsStore } from '../store/insightsStore';
import { type InsightItem } from '../store/uiStore';

export function useNodeInsights(nodeId: string | null) {
  const insightsByNode = useInsightsStore((s) => s.insightsByNode);
  const loadingByNode = useInsightsStore((s) => s.loadingByNode);
  const fetchInsights = useInsightsStore((s) => s.fetchInsights);

  const insights = nodeId && nodeId !== 'all' ? insightsByNode[nodeId] || [] : [];
  const loading = nodeId && nodeId !== 'all' ? loadingByNode[nodeId] || false : false;

  const refresh = useCallback(() => {
    if (nodeId && nodeId !== 'all') {
      fetchInsights(nodeId);
    }
  }, [nodeId, fetchInsights]);

  useEffect(() => {
    if (nodeId && nodeId !== 'all') {
      fetchInsights(nodeId);
    }
  }, [nodeId, fetchInsights]);

  return {
    insights,
    loading,
    refresh,
  };
}
export type { InsightItem };
