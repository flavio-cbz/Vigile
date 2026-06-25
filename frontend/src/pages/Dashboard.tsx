import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Server as ServerIcon, Layers, Sparkles, Activity, CheckSquare, Grid3x3, Plus } from 'lucide-react';

import { useNodeStore } from '../store/nodeStore';
import { useUiStore } from '../store/uiStore';
import type { ActionProposal, InsightItem } from '../store/uiStore';
import { useInsightsStore } from '../store/insightsStore';
import { useChatStore } from '../store/chatStore';
import { useLayoutStore } from '../store/layoutStore';

import { HeroBanner } from '../components/dashboard/HeroBanner';
import { SwimLane } from '../components/dashboard/SwimLane';
import { ServerCard } from '../components/dashboard/ServerCard';
import { ContainerCard } from '../components/dashboard/ContainerCard';
import { InsightCard } from '../components/dashboard/InsightCard';
import { ProposalCard } from '../components/dashboard/ProposalCard';
import { ActivityItem } from '../components/dashboard/ActivityItem';
import { TrendChart } from '../components/dashboard/TrendChart';
import { FleetGrid } from '../components/dashboard/FleetGrid';

import { usePolling } from '../hooks/usePolling';
import { api } from '../hooks/useApi';
import { Spinner } from '../components/primitives/Spinner';
import { usePageTitle } from '../hooks/usePageTitle';
import { formatActorName } from '../utils/formatActor';
import { useLocale } from '../i18n';

interface ContainerItem {
  id: string;
  name: string;
  image: string;
  state: string;
  status: string;
  nodeId: string;
  nodeName: string;
}

// Helper to resolve the highest priority active insight for a node: critical > warning > info
const getTopInsight = (insights?: InsightItem[] | null): InsightItem | null => {
  if (!insights || insights.length === 0) return null;
  const severityOrder: Record<string, number> = { critical: 3, warning: 2, info: 1 };

  // Filter for insights that deserve attention (critical, warning, info)
  const activeInsights = insights.filter(ins => ins.severity in severityOrder);
  if (activeInsights.length === 0) return null;

  return [...activeInsights].sort((a, b) => {
    const aVal = severityOrder[a.severity] || 0;
    const bVal = severityOrder[b.severity] || 0;
    return bVal - aVal; // Descending
  })[0] || null;
};

export const Dashboard: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.dashboard'));
  const navigate = useNavigate();
  const { nodes, isLoading: loadingNodes, fetchNodes } = useNodeStore();
  const { openCopilot } = useUiStore();
  const { fetchInsights, insightsByNode } = useInsightsStore();

  const [bulkStatus, setBulkStatus] = useState<Record<string, any>>({});
  const [proposals, setProposals] = useState<ActionProposal[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [containers, setContainers] = useState<ContainerItem[]>([]);

  const relevantActions = new Set([
    'PROPOSAL_APPROVED', 'PROPOSAL_REJECTED',
    'NODE_LOST', 'NODE_STALE', 'NODE_RECONNECTED', 'NODE_ENROLLED',
    'RESTART_SERVICE', 'RESTART_CONTAINER'
  ]);
  const [loadingDashboard, setLoadingDashboard] = useState(true);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [loadingContainers, setLoadingContainers] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  const [loadingProposalId, setLoadingProposalId] = useState<string | null>(null);
  const [rejectingProposalId, setRejectingProposalId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [showChart, setShowChart] = useState(false);

  const fetchBulkMetrics = async () => {
    try {
      const data = await api<{ statuses: Record<string, any> }>('/api/nodes/bulk/status');
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
      const data = await api<{ entries: any[] }>('/api/audit?limit=20');
      if (data && data.entries) {
        const filtered = data.entries
          .filter(e => relevantActions.has(e.action))
          .slice(0, 8);
        setActivity(filtered);
      }
    } catch (err) {
      console.error('Failed to fetch recent audit activity:', err);
    }
  };

  const fetchAllContainers = async () => {
    const onlineNodes = nodes.filter(n => n.online);
    if (onlineNodes.length === 0) {
      setContainers([]);
      return;
    }
    setLoadingContainers(true);
    try {
      const containerPromises = onlineNodes.map(async (node) => {
        try {
          const res = await api<{ containers: any[] }>(`/api/nodes/${node.id}/containers`, { skipToast: true });
          if (res && res.containers) {
            return res.containers.map(c => ({
              ...c,
              nodeId: node.id,
              nodeName: node.name
            }));
          }
        } catch (err) {
          console.error(`Failed to fetch containers for node ${node.name}:`, err);
        }
        return [];
      });

      const results = await Promise.all(containerPromises);
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

      setContainers(sorted);
    } catch (err) {
      console.error('Failed to aggregate containers:', err);
    } finally {
      setLoadingContainers(false);
    }
  };

  useEffect(() => {
    const loadAll = async () => {
      setLoadingDashboard(true);
      setInsightsLoading(true);
      await fetchNodes();
      await Promise.all([
        fetchBulkMetrics(),
        fetchProposalsList(),
        fetchRecentActivity(),
      ]);

      const currentNodes = useNodeStore.getState().nodes;
      const onlineNodes = currentNodes.filter(n => n.online && n.id);
      if (onlineNodes.length > 0) {
        await Promise.allSettled(
          onlineNodes.map(n => fetchInsights(n.id))
        );
      }
      setInsightsLoading(false);
      setLoadingDashboard(false);
    };

    loadAll();
  }, []);

  useEffect(() => {
    if (nodes.length > 0) {
      fetchAllContainers();
    }
  }, [nodes]);

  usePolling('bulk_metrics_poll', fetchBulkMetrics, 15000);
  usePolling('dashboard_proposals_poll', fetchProposalsList, 30000);
  usePolling('dashboard_activity_poll', fetchRecentActivity, 30000);
  usePolling('dashboard_containers_poll', fetchAllContainers, 45000);

  // Combine all insights into a flat list (includes real + synthetic offline insights)
  const allInsightsList: Array<{ insight: any; nodeName: string; nodeId: string }> = [];
  let stableMetricsCount = 0;

  Object.entries(insightsByNode).forEach(([nodeId, list]) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return;
    list.forEach((insight) => {
      if (insight.severity === 'ok') {
        stableMetricsCount++;
      } else {
        allInsightsList.push({ insight, nodeName: node.name, nodeId });
      }
    });
  });

  nodes
    .filter(n => !n.online)
    .forEach(n => {
      const hbTime = n.last_heartbeat;
      const hbLabel = hbTime
        ? new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString('fr-FR')
        : null;

      allInsightsList.unshift({
        insight: {
          type: 'offline',
          severity: 'offline' as const,
          icon: '📡',
          headline: hbTime
            ? t('dash.insight_offline_headline', { time: hbLabel ?? '' })
            : t('dash.insight_offline_headline_no_hb'),
          detail: hbTime
            ? t('dash.insight_offline_detail', { time: hbLabel ?? '' })
            : t('dash.insight_offline_detail_no_hb'),
          raw: {
            last_heartbeat: hbTime,
          },
        },
        nodeName: n.name,
        nodeId: n.id,
      });
    });

  const handleApproveProposal = async (id: string) => {
    setLoadingProposalId(id);
    try {
      const success = await useChatStore.getState().approveProposal(id);
      if (success) {
        await Promise.all([fetchProposalsList(), fetchRecentActivity()]);
      }
    } finally {
      setLoadingProposalId(null);
    }
  };

  const handleRejectInit = (id: string) => {
    setRejectingProposalId(id);
    setRejectReason('');
  };

  const formatUptime = (seconds: number | undefined): string => {
    if (seconds === undefined || seconds === null) return 'N/A';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const minutes = seconds / 60;
    if (minutes < 60) return `${Math.round(minutes)}m`;
    const hours = minutes / 60;
    if (hours < 24) return `${Math.round(hours)}h`;
    const days = hours / 24;
    return `${Math.round(days)}j`;
  };

  if (loadingDashboard || loadingNodes) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-text-3 font-interface text-xs select-none">
        <Spinner size="md" />
        <span>{t('dash.loading_hud')}</span>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center select-none animate-fade-in">
        <div className="card max-w-md w-full py-12 px-8 text-center flex flex-col items-center gap-5">
          <div className="w-14 h-14 rounded-xl bg-accent-muted/15 border border-accent/30 flex items-center justify-center shadow-[0_0_18px_var(--color-accent-glow)]">
            <ServerIcon className="w-7 h-7 text-accent" />
          </div>
          <div className="space-y-1.5">
            <h2 className="text-base font-bold font-interface text-text-1 uppercase tracking-wider">
              {t('dash.empty_title')}
            </h2>
            <p className="text-xs text-text-2 leading-relaxed max-w-sm mx-auto">
              {t('dash.empty_description')}
            </p>
          </div>
          <button
            type="button"
            onClick={() => useLayoutStore.getState().setAddNodeModalOpen(true)}
            className="btn btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-xs font-interface font-semibold cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            {t('dash.empty_action')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8 pb-10 animate-fade-in">
      <HeroBanner nodes={nodes} lastUpdated={lastUpdated} />

      {insightsLoading ? (
        <SwimLane
          title={t('swim.insights')}
          icon={Sparkles}
          layout="grid"
        >
          {[1, 2, 3].map(i => (
            <div key={i} className="card card-insight animate-pulse flex flex-col justify-between">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="h-4 w-16 bg-surface-2 rounded" />
                <div className="h-4 w-20 bg-surface-2 rounded" />
              </div>
              <div className="space-y-2">
                <div className="h-5 bg-surface-2 rounded w-full" />
                <div className="h-5 bg-surface-2 rounded w-4/5" />
                <div className="h-3 bg-surface-2 rounded w-3/5 mt-2" />
              </div>
            </div>
          ))}
        </SwimLane>
      ) : allInsightsList.length > 0 ? (
        <SwimLane
          title={t('swim.insights')}
          icon={Sparkles}
          layout="grid"
          subtitle={stableMetricsCount > 0 ? `• ${stableMetricsCount} métrique${stableMetricsCount > 1 ? 's' : ''} stable${stableMetricsCount > 1 ? 's' : ''} sur la flotte` : undefined}
        >
          {allInsightsList.map((item, idx) => (
            <InsightCard
              key={`${item.nodeId}-${item.insight.type}-${idx}`}
              insight={item.insight}
              nodeName={item.nodeName}
              nodeId={item.nodeId}
              onDiagnose={() =>
                openCopilot({
                  trigger: 'diagnostic',
                  insight: item.insight,
                  node_id: item.nodeId,
                })
              }
            />
          ))}
        </SwimLane>
      ) : stableMetricsCount > 0 ? (
        <div className="px-4 md:px-12">
          <div className="flex items-center gap-2 text-xs text-success bg-success/5 border border-success/15 rounded-lg py-2.5 px-4 w-fit">
            <span className="text-sm">✓</span>
            <span className="font-interface font-medium">
              {t('dash.stable_metrics', { count: stableMetricsCount })}
            </span>
          </div>
        </div>
      ) : null}

      <SwimLane
        title={t('dash.your_servers')}
        icon={ServerIcon}
        isLoading={nodes.length === 0}
        layout="grid"
        className={(allInsightsList.length > 0 || stableMetricsCount > 0) ? 'border-t border-border/30 pt-6 mt-6' : undefined}
      >
        {nodes.map((node) => {
          const stats = bulkStatus[node.id];
          const nodeInsights = insightsByNode[node.id];
          const topInsight = getTopInsight(nodeInsights);
          return (
            <ServerCard
              key={node.id}
              node={node}
              metrics={
                stats
                  ? {
                      cpu: stats.cpu,
                      mem: stats.mem,
                      disk: stats.disk,
                      uptime: formatUptime(stats.uptime),
                      loading: false,
                    }
                  : undefined
              }
              topInsight={topInsight}
              onClick={() => navigate(`/nodes/${node.id}`)}
            />
          );
        })}
      </SwimLane>

      {proposals.length > 0 && (
        <SwimLane
          title={t('dash.proposed_actions')}
          icon={CheckSquare}
          className="border-t border-border/30 pt-6 mt-6"
          layout="grid"
        >
          {proposals.map((prop) => {
            const node = nodes.find((n) => n.id === prop.node_id);
            return (
              <ProposalCard
                key={prop.id}
                proposal={prop}
                nodeName={node ? node.name : t('common.system')}
                onApprove={handleApproveProposal}
                onReject={async (id) => handleRejectInit(id)}
                loading={loadingProposalId === prop.id}
              />
            );
          })}
        </SwimLane>
      )}

      <SwimLane
        title={t('dash.containers')}
        icon={Layers}
        isLoading={loadingContainers && containers.length === 0}
        className="border-t border-border/30 pt-6 mt-6"
      >
        {containers.map((container) => (
          <ContainerCard
            key={`${container.nodeId}-${container.id}`}
            nodeId={container.nodeId}
            nodeName={container.nodeName}
            container={container}
            onRefresh={fetchAllContainers}
          />
        ))}
      </SwimLane>

      {activity.length > 0 && (
        <div className="space-y-3 relative w-full border-t border-border/30 pt-6 mt-6 animate-fade-in">
          <div className="flex items-center justify-between px-4 md:px-12">
            <div className="flex items-center gap-2">
              <Activity className="text-accent w-4.5 h-4.5" />
              <h3 className="text-sm font-bold text-text-1 tracking-wide uppercase">
                {t('swim.activity')}
              </h3>
            </div>
          </div>

          <div className="px-4 md:px-12">
            <div className="border border-border rounded-xl bg-surface divide-y divide-border overflow-hidden shadow-md">
              {activity.map((act) => (
                <ActivityItem
                  key={act.id}
                  action={act.action}
                  actor={formatActorName(act.actor || act.user_id)}
                  userId={act.user_id}
                  timestamp={act.timestamp}
                  details={act.details}
                  nodeId={act.node_id}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      <SwimLane
        title={t('dash.fleet_status')}
        icon={Grid3x3}
        layout="grid"
        className="border-t border-border-strong pt-6 mt-6"
      >
        {!showChart ? (
          <FleetGrid
            nodes={nodes}
            bulkStatus={bulkStatus}
            insightsByNode={insightsByNode}
            onNodeClick={(id) => navigate(`/nodes/${id}`)}
          />
        ) : (
          <TrendChart nodes={nodes} />
        )}
      </SwimLane>
      <div className="flex justify-end px-4 md:px-12 -mt-4">
        <button
          type="button"
          onClick={() => setShowChart(!showChart)}
          className="text-xs text-accent hover:underline font-interface font-semibold cursor-pointer transition-colors"
        >
          {showChart ? t('dash.toggle_grid') : t('dash.toggle_trends')}
        </button>
      </div>

      {rejectingProposalId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs select-none animate-fade-in">
          <div className="w-full max-w-md p-6 bg-surface border border-border rounded-xl shadow-2xl space-y-4">
            <div>
              <h3 className="text-sm font-bold text-text-1 font-interface uppercase tracking-wider">
                {t('dash.reject_reason_title')}
              </h3>
              <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
                {t('dash.reject_reason_description')}
              </p>
            </div>

            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder={t('dash.reject_reason_placeholder')}
              className="w-full h-24 bg-surface-2 border border-border focus:border-accent/40 rounded-lg p-3 text-xs text-text-1 placeholder:text-text-3 focus:outline-none resize-none font-sans"
              autoFocus
            />

            <div className="flex justify-end gap-2.5 font-interface text-[10px] font-bold">
              <button
                type="button"
                onClick={() => {
                  setRejectingProposalId(null);
                  setRejectReason('');
                }}
                className="px-4 py-2 border border-border hover:border-border-strong text-text-2 rounded-lg cursor-pointer transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                disabled={!rejectReason.trim()}
                onClick={async () => {
                  const id = rejectingProposalId;
                  const reason = rejectReason;
                  setRejectingProposalId(null);
                  setRejectReason('');
                  setLoadingProposalId(id);
                  try {
                    const success = await useChatStore.getState().rejectProposal(id, reason);
                    if (success) {
                      await fetchProposalsList();
                    }
                  } catch (err) {
                    console.error('Failed to reject proposal:', err);
                  } finally {
                    setLoadingProposalId(null);
                  }
                }}
                className="px-4 py-2 bg-severity-critical text-text-1 hover:bg-severity-critical/80 rounded-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {t('dash.reject_confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
