import React, { useState } from 'react';
import { useNavigate } from 'react-router';

import { useNodeStore } from '../store/nodeStore';
import { useUiStore } from '../store/uiStore';
import type { InsightItem } from '../store/uiStore';
import { useInsightsStore } from '../store/insightsStore';

import { HeroBanner } from '../components/dashboard/HeroBanner';
import { useDashboardData } from '../hooks/useDashboardData';
import { usePageTitle } from '../hooks/usePageTitle';
import { useLocale } from '../i18n';

import { DashboardSkeleton } from '../components/dashboard/DashboardSkeleton';
import { InsightsSection } from '../components/dashboard/InsightsSection';
import { ServersSection } from '../components/dashboard/ServersSection';
import { ProposalsSection } from '../components/dashboard/ProposalsSection';
import { ContainersSection } from '../components/dashboard/ContainersSection';
import { ActivitySection } from '../components/dashboard/ActivitySection';
import { FleetSection } from '../components/dashboard/FleetSection';

// Helper to resolve the highest priority active insight for a node: critical > warning > info
const getTopInsight = (insights?: InsightItem[] | null): InsightItem | null => {
  if (!insights || insights.length === 0) return null;
  const severityOrder: Record<string, number> = { critical: 3, warning: 2, info: 1 };

  // Filter for insights that deserve attention (critical, warning, info)
  const activeInsights = insights.filter((ins) => ins.severity in severityOrder);
  if (activeInsights.length === 0) return null;

  return [...activeInsights].sort((a, b) => {
    const aVal = severityOrder[a.severity] || 0;
    const bVal = severityOrder[b.severity] || 0;
    return bVal - aVal; // Descending
  })[0] || null;
};

const formatUptime = (seconds: number | undefined): string => {
  if (seconds === undefined || seconds === null) return 'N/A';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = Math.floor(hours / 24);
  const remainingHours = Math.round(hours % 24);
  return `${days}j ${remainingHours}h`;
};

export const Dashboard: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.dashboard'));
  const navigate = useNavigate();
  const { nodes, isLoading: loadingNodes } = useNodeStore();
  const { openCopilot } = useUiStore();
  const { insightsByNode } = useInsightsStore();

  const {
    bulkStatus,
    proposals,
    activity,
    containers,
    loadingDashboard,
    insightsLoading,
    loadingContainers,
    lastUpdated,
    fetchAllContainers,
    handleApproveProposal,
    handleRejectProposal,
  } = useDashboardData();

  const [showChart, setShowChart] = useState(false);
  const [rejectingProposalId, setRejectingProposalId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [loadingProposalId, setLoadingProposalId] = useState<string | null>(null);
  const [removingProposalId, setRemovingProposalId] = useState<string | null>(null);

  // Combine all insights into a flat list (includes real + synthetic offline insights)
  const allInsightsList: Array<{ insight: InsightItem; nodeName: string; nodeId: string }> = [];
  let stableMetricsCount = 0;

  Object.entries(insightsByNode).forEach(([nodeId, list]) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return;
    list.forEach((insight) => {
      allInsightsList.push({ insight, nodeName: node.name, nodeId });
      if (insight.severity === 'ok') {
        stableMetricsCount++;
      }
    });
  });

  nodes
    .filter((n) => !n.online)
    .forEach((n) => {
      const hbTime = n.last_heartbeat;
      const hbLabel = hbTime
        ? new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString('fr-FR')
        : null;

      allInsightsList.unshift({
        insight: {
          type: 'offline',
          severity: 'offline',
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

  if (loadingDashboard || loadingNodes || nodes.length === 0) {
    return <DashboardSkeleton loading={loadingDashboard || loadingNodes} hasNodes={nodes.length > 0} />;
  }

  const hasInsightContent = allInsightsList.length > 0 || stableMetricsCount > 0;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8 pb-10 animate-fade-in">
      <HeroBanner nodes={nodes} lastUpdated={lastUpdated} />

      <InsightsSection
        loading={insightsLoading}
        insights={allInsightsList}
        stableMetricsCount={stableMetricsCount}
        onDiagnose={(insight, nodeId) =>
          openCopilot({ trigger: 'diagnostic', insight, node_id: nodeId })
        }
      />

      <ServersSection
        nodes={nodes}
        bulkStatus={bulkStatus}
        insightsByNode={insightsByNode}
        hasInsightContent={hasInsightContent}
        onNodeClick={(id) => navigate(`/nodes/${id}`)}
        getTopInsight={getTopInsight}
        formatUptime={formatUptime}
      />

      <ProposalsSection
        proposals={proposals}
        nodes={nodes}
        loadingProposalId={loadingProposalId}
        rejectingProposalId={rejectingProposalId}
        rejectReason={rejectReason}
        removingProposalId={removingProposalId}
        onApprove={async (id) => {
          setLoadingProposalId(id);
          try {
            await handleApproveProposal(id);
          } finally {
            setLoadingProposalId(null);
          }
        }}
        onRejectInit={(id) => {
          setRejectingProposalId(id);
          setRejectReason('');
        }}
        onRejectCancel={() => {
          setRejectingProposalId(null);
          setRejectReason('');
        }}
        onRejectChange={setRejectReason}
        onRejectConfirm={async (id, reason) => {
          setRejectingProposalId(null);
          setRejectReason('');
          setLoadingProposalId(id);
          // Start exit animation before removing
          setRemovingProposalId(id);
          await new Promise(resolve => setTimeout(resolve, 600));
          try {
            await handleRejectProposal(id, reason);
          } finally {
            setLoadingProposalId(null);
            setRemovingProposalId(null);
          }
        }}
      />

      <ContainersSection
        containers={containers}
        isLoading={loadingContainers}
        onRefresh={fetchAllContainers}
      />

      <ActivitySection entries={activity} />

      <FleetSection
        nodes={nodes}
        bulkStatus={bulkStatus}
        insightsByNode={insightsByNode}
        showChart={showChart}
        onToggle={() => setShowChart((v) => !v)}
        onNodeClick={(id) => navigate(`/nodes/${id}`)}
      />
    </div>
  );
};
