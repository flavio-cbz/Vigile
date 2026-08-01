import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from './useApi';
import { usePolling } from './usePolling';
import { useChatStore } from '../store/chatStore';
import { useInsightsStore } from '../store/insightsStore';
import { useNodeStore } from '../store/nodeStore';
import type { ActionProposal } from '../store/uiStore';

export interface ContainerItem {
  id: string;
  name: string;
  image: string;
  state: string;
  status: string;
  nodeId: string;
  nodeName: string;
}

export interface ActivityEntry {
  id: string;
  action: string;
  actor?: string;
  user_id?: string;
  timestamp: number;
  details?: Record<string, unknown>;
  node_id?: string;
}

interface BulkStatusPayload {
  statuses: Record<string, {
    cpu?: number;
    mem?: number;
    disk?: number;
    uptime?: number;
  }>;
}

const RELEVANT_ACTIONS = new Set<string>([
  'PROPOSAL_APPROVED',
  'PROPOSAL_REJECTED',
  'NODE_LOST',
  'NODE_STALE',
  'NODE_RECONNECTED',
  'NODE_ENROLLED',
  'RESTART_SERVICE',
  'RESTART_CONTAINER',
]);

/**
 * Runs `fn` over `items` with at most `limit` concurrent invocations,
 * preserving input order in the results (worker-pool pattern).
 */
async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;

  const worker = async () => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await fn(items[index]);
    }
  };

  const workerCount = Math.min(limit, items.length);
  await Promise.all(
    Array.from({ length: workerCount }, () => worker()),
  );
  return results;
}

/**
 * Encapsulates all Dashboard data fetching, polling, and the imperative
 * proposal approval/rejection flows. The component consumes the returned
 * state and helpers to render.
 */
export function useDashboardData() {
  const { nodes, isLoading: loadingNodes, fetchNodes } = useNodeStore();
  const { fetchInsights } = useInsightsStore();

  const [bulkStatus, setBulkStatus] = useState<Record<string, BulkStatusPayload['statuses'][string]>>({});
  const [proposals, setProposals] = useState<ActionProposal[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [containers, setContainers] = useState<ContainerItem[]>([]);

  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [loadingContainers, setLoadingContainers] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  const containersRef = useRef<ContainerItem[]>([]);

  const fetchBulkMetrics = async () => {
    try {
      const data = await api<BulkStatusPayload>('/api/nodes/bulk/status');
      if (data && data.statuses) {
        setBulkStatus(data.statuses);
        setLastUpdated(Date.now());
      }
    } catch (err) {
      console.error('Failed to fetch bulk statuses:', err);
    }
  };

  const fetchProposalsList = async () => {
    try {
      const data = await api<ActionProposal[]>('/api/chat/proposals?status=PENDING');
      if (data) {
        setProposals(data);
      }
    } catch (err) {
      console.error('Failed to fetch proposals list:', err);
    }
  };

  const fetchRecentActivity = async () => {
    try {
      const data = await api<{ entries: ActivityEntry[] }>('/api/audit?limit=20');
      if (data && data.entries) {
        const filtered = data.entries
          .filter((e) => RELEVANT_ACTIONS.has(e.action))
          .slice(0, 8);
        setActivity(filtered);
      }
    } catch (err) {
      console.error('Failed to fetch recent audit activity:', err);
    }
  };

  const fetchAllContainers = useCallback(async () => {
    const currentNodes = useNodeStore.getState().nodes;
    const onlineNodes = currentNodes.filter((n) => n.online);
    if (onlineNodes.length === 0) {
      if (containersRef.current.length > 0) {
        containersRef.current = [];
        setContainers([]);
      }
      return;
    }
    // Loading skeleton only meaningful on the initial (empty) load; background
    // polls with existing data skip the flag to avoid 2 churn re-renders/cycle.
    const showLoading = containersRef.current.length === 0;
    if (showLoading) {
      setLoadingContainers(true);
    }
    try {
      const results = await mapWithConcurrency(onlineNodes, 3, async (node) => {
        try {
          const res = await api<{ containers: Omit<ContainerItem, 'nodeId' | 'nodeName'>[] }>(
            `/api/nodes/${node.id}/containers`,
            { skipToast: true },
          );
          if (res && res.containers) {
            return res.containers.map((c) => ({
              ...c,
              nodeId: node.id,
              nodeName: node.name,
            }));
          }
        } catch (err) {
          console.error(`Failed to fetch containers for node ${node.name}:`, err);
        }
        return [];
      });

      const flattened = results.flat();

      // Sort exited/stopped first, then running
      const sorted = flattened.sort((a, b) => {
        const aState = (a.state ?? '').toLowerCase();
        const aStatus = (a.status ?? '').toLowerCase();
        const bState = (b.state ?? '').toLowerCase();
        const bStatus = (b.status ?? '').toLowerCase();
        const aRunning = aState === 'running' || aStatus.includes('up');
        const bRunning = bState === 'running' || bStatus.includes('up');
        if (aRunning && !bRunning) return 1;
        if (!aRunning && bRunning) return -1;
        return (a.name ?? '').localeCompare(b.name ?? '');
      });

      const prev = containersRef.current;
      const unchanged =
        prev.length === sorted.length &&
        prev.every((c, i) =>
          c.id === sorted[i].id && c.state === sorted[i].state && c.status === sorted[i].status
        );
      if (unchanged) return;

      containersRef.current = sorted;
      setContainers(sorted);
    } catch (err) {
      console.error('Failed to aggregate containers:', err);
    } finally {
      if (showLoading) {
        setLoadingContainers(false);
      }
    }
  }, []);

  // Initial load: nodes -> bulk metrics + proposals + activity -> insights
  useEffect(() => {
    // loadingDashboard && insightsLoading already true from useState initializer
    const loadAll = async () => {
      await fetchNodes();
      await Promise.all([
        fetchBulkMetrics(),
        fetchProposalsList(),
        fetchRecentActivity(),
      ]);

      const currentNodes = useNodeStore.getState().nodes;
      const onlineNodes = currentNodes.filter((n) => n.online && n.id);
      if (onlineNodes.length > 0) {
        await Promise.allSettled(
          onlineNodes.map((n) => fetchInsights(n.id)),
        );
      }
      setInsightsLoading(false);
      setLoadingDashboard(false);
    };

    loadAll();
    // Intentionally run once on mount; subsequent updates are handled by polling
    // and the nodes-change effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-aggregate containers whenever the online node set changes
  const onlineNodeIds = useMemo(
    () => nodes.filter(n => n.online).map(n => n.id).join(','),
    [nodes]
  );

  useEffect(() => {
    if (onlineNodeIds) {
      void fetchAllContainers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onlineNodeIds]);

  usePolling('bulk_metrics_poll', fetchBulkMetrics, 20000);
  usePolling('dashboard_proposals_poll', fetchProposalsList, 45000);
  usePolling('dashboard_activity_poll', fetchRecentActivity, 45000);
  usePolling('dashboard_containers_poll', fetchAllContainers, 60000);

  const handleApproveProposal = async (id: string) => {
    try {
      const success = await useChatStore.getState().approveProposal(id);
      if (success) {
        await Promise.all([fetchProposalsList(), fetchRecentActivity()]);
      }
      return success;
    } catch (err) {
      console.error('Failed to approve proposal:', err);
      return false;
    }
  };

  const handleRejectProposal = async (id: string, reason: string) => {
    try {
      const success = await useChatStore.getState().rejectProposal(id, reason);
      if (success) {
        await fetchProposalsList();
      }
      return success;
    } catch (err) {
      console.error('Failed to reject proposal:', err);
      return false;
    }
  };

  return {
    bulkStatus,
    proposals,
    activity,
    containers,
    loadingDashboard,
    insightsLoading,
    loadingContainers,
    loadingNodes,
    lastUpdated,
    fetchProposalsList,
    fetchAllContainers,
    handleApproveProposal,
    handleRejectProposal,
  };
}
