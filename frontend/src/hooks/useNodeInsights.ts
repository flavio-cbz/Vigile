import { useEffect, useCallback, useRef } from 'react';
import { useInsightsStore } from '../store/insightsStore';
import { useUiStore, type InsightItem } from '../store/uiStore';

export function useNodeInsights(nodeId: string | null) {
  const { insightsByNode, loadingByNode, fetchInsights } = useInsightsStore();
  const { openCopilot } = useUiStore();

  const insights = nodeId && nodeId !== 'all' ? insightsByNode[nodeId] || [] : [];
  const loading = nodeId && nodeId !== 'all' ? loadingByNode[nodeId] || false : false;

  const refresh = useCallback(() => {
    if (nodeId && nodeId !== 'all') {
      fetchInsights(nodeId);
    }
  }, [nodeId, fetchInsights]);

  // Track auto-opened insight keys to prevent infinite re-triggering
  const autoOpenedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (nodeId && nodeId !== 'all') {
      fetchInsights(nodeId);
    }
  }, [nodeId, fetchInsights]);

  useEffect(() => {
    if (!nodeId || nodeId === 'all' || loading || insights.length === 0) return;

    const targetInsight = insights.find(
      (ins) => ins.severity === 'critical' || ins.severity === 'warning'
    );

    if (targetInsight) {
      const key = `${nodeId}-${targetInsight.type}-${targetInsight.headline}`;
      if (!autoOpenedRef.current.has(key)) {
        autoOpenedRef.current.add(key);
        openCopilot({
          trigger: 'insight',
          node_id: nodeId,
          insight: targetInsight,
        });
      }
    }
  }, [nodeId, insights, loading, openCopilot]);

  return {
    insights,
    loading,
    refresh,
  };
}
export type { InsightItem };
