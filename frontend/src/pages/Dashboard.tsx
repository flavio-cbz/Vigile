import React, { useState, useMemo } from 'react';
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

import { RecommendedCard } from '../components/dashboard/RecommendedCard';

// Helper to resolve the highest priority active insight for a node: critical > warning > info
const getTopInsight = (insights?: InsightItem[] | null): InsightItem | null => {
  if (!insights || insights.length === 0) return null;
  const critical = insights.find((i) => i.severity === 'critical');
  if (critical) return critical;
  const warning = insights.find((i) => i.severity === 'warning');
  if (warning) return warning;
  const info = insights.find((i) => i.severity === 'info');
  return info || null;
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
  const nodes = useNodeStore((s) => s.nodes);
  const loadingNodes = useNodeStore((s) => s.isLoading);
  const openCopilot = useUiStore((s) => s.openCopilot);
  const insightsByNode = useInsightsStore((s) => s.insightsByNode);

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
  const { allInsightsList, stableMetricsCount } = useMemo(() => {
    const listArr: Array<{ insight: InsightItem; nodeName: string; nodeId: string }> = [];
    let stableCount = 0;

    Object.entries(insightsByNode).forEach(([nodeId, list]) => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return;
      list.forEach((insight) => {
        listArr.push({ insight, nodeName: node.name, nodeId });
        if (insight.severity === 'ok') {
          stableCount++;
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

        listArr.unshift({
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

    return { allInsightsList: listArr, stableMetricsCount: stableCount };
  }, [insightsByNode, nodes, t]);

  // Find top actionable insight (critical > warning)
  const topActionableEntry = useMemo(() => allInsightsList.find(
    (item) => item.insight.severity === 'critical' || item.insight.severity === 'warning'
  ) || null, [allInsightsList]);

  if (loadingDashboard || loadingNodes || nodes.length === 0) {
    return <DashboardSkeleton loading={loadingDashboard || loadingNodes} hasNodes={nodes.length > 0} />;
  }

  const hasInsightContent = allInsightsList.length > 0 || stableMetricsCount > 0;
  const topInsightForBanner = topActionableEntry ? topActionableEntry.insight : null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8 pb-10 animate-fade-in">
      {/* 1. Decision banner */}
      <HeroBanner nodes={nodes} lastUpdated={lastUpdated} topInsight={topInsightForBanner} />

      {/* 2. Recommended card */}
      {topActionableEntry && (
        <RecommendedCard
          insight={topActionableEntry.insight}
          nodeName={topActionableEntry.nodeName}
          onUnderstand={() =>
            openCopilot({
              trigger: 'diagnostic',
              insight: topActionableEntry.insight,
              node_id: topActionableEntry.nodeId,
            })
          }
          onPrepareProposal={() =>
            openCopilot({
              trigger: 'action',
              insight: topActionableEntry.insight,
              node_id: topActionableEntry.nodeId,
            })
          }
        />
      )}

      {/* 3. Actionable insights section */}
      <InsightsSection
        loading={insightsLoading}
        insights={allInsightsList}
        stableMetricsCount={stableMetricsCount}
        onDiagnose={(insight, nodeId) =>
          openCopilot({ trigger: 'diagnostic', insight, node_id: nodeId })
        }
      />

      {/* 4. Pending proposals section */}
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

      {/* 5. Servers section */}
      <ServersSection
        nodes={nodes}
        bulkStatus={bulkStatus}
        insightsByNode={insightsByNode}
        hasInsightContent={hasInsightContent}
        onNodeClick={(id) => navigate(`/nodes/${id}`)}
        getTopInsight={getTopInsight}
        formatUptime={formatUptime}
      />

      {/* 6. Abnormal containers */}
      <ContainersSection
        containers={containers}
        isLoading={loadingContainers}
        onRefresh={fetchAllContainers}
      />

      {/* 7. Fleet Section / Capacity Trends (if > 1 node show fleet grid, else capacity trend) */}
      {nodes.length > 1 && (
        <FleetSection
          nodes={nodes}
          bulkStatus={bulkStatus}
          insightsByNode={insightsByNode}
          showChart={showChart}
          onToggle={() => setShowChart((v) => !v)}
          onNodeClick={(id) => navigate(`/nodes/${id}`)}
        />
      )}

      {/* 8. Recent activity */}
      <ActivitySection entries={activity} />
    </div>
  );
};
