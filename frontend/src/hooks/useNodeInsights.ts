import { useEffect, useCallback } from 'react';
import { useInsightsStore } from '../store/insightsStore';
import { type InsightItem } from '../store/uiStore';
import type { InsightsMeta } from '../components/node-detail/types';

export function useNodeInsights(nodeId: string | null) {
  const insightsByNode = useInsightsStore((s) => s.insightsByNode);
  const loadingByNode = useInsightsStore((s) => s.loadingByNode);
  const metaByNode = useInsightsStore((s) => s.metaByNode);
  const fetchInsights = useInsightsStore((s) => s.fetchInsights);

  const insights = nodeId && nodeId !== 'all' ? insightsByNode[nodeId] || [] : [];
  const loading = nodeId && nodeId !== 'all' ? loadingByNode[nodeId] || false : false;
  const meta: InsightsMeta | null = nodeId && nodeId !== 'all' ? metaByNode[nodeId] || null : null;

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
    meta,
  };
}
export type { InsightItem };
