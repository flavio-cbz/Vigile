import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router';
import { usePolling } from '../hooks/usePolling';
import { Spinner } from '../components/primitives/Spinner';
import { api } from '../hooks/useApi';
import { usePermission } from '../hooks/usePermission';
import { usePageTitle } from '../hooks/usePageTitle';
import { useLocale } from '../i18n';
import { useNodeDetailData } from '../hooks/useNodeDetailData';
import { ArrowLeft } from 'lucide-react';
import { NodeSettingsTab } from '../components/dashboard/NodeSettingsTab';
import { NodeDetailHeader } from '../components/node-detail/NodeDetailHeader';
import { NodeDetailTabs, useNodeDetailTabs } from '../components/node-detail/NodeDetailTabs';
import { NodeDetailMetricsTab } from '../components/node-detail/NodeDetailMetricsTab';
import { NodeDetailLogsTab } from '../components/node-detail/NodeDetailLogsTab';
import { NodeDetailServicesTab } from '../components/node-detail/NodeDetailServicesTab';
import { NodeDetailContainersTab } from '../components/node-detail/NodeDetailContainersTab';
import { NodeDetailInsightsTab } from '../components/node-detail/NodeDetailInsightsTab';
import type { NodeDetailTabId } from '../components/node-detail/types';

export const NodeDetail: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.node_detail'));
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { isAdmin, can } = usePermission();
  const isAdminOrOperator = can('approve-action');

  const data = useNodeDetailData(id);
  const {
    node,
    loadingNode,
    displayInsights,
    loadingInsights,
    refreshInsights,
    statsHistory,
    loadingStats,
    fetchStatsHistory,
    services,
    loadingServices,
    fetchServicesList,
    containers,
    loadingContainers,
    fetchContainersList,
    logs,
    loadingLogs,
    logsService,
    setLogsService,
    logsLimit,
    setLogsLimit,
    logsAutoScroll,
    setLogsAutoScroll,
    fetchNodeLogs,
    restartingService,
    setRestartingService,
    restartingContainer,
    setRestartingContainer,
  } = data;

  const [activeTab, setActiveTab] = useState<NodeDetailTabId>('insights');
  const [searchParams] = useSearchParams();
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam && ['insights', 'metrics', 'services', 'containers', 'logs', 'settings'].includes(tabParam)) {
      setActiveTab(tabParam as NodeDetailTabId);
    }
  }, [searchParams]);

  useEffect(() => {
    if (activeTab === 'services' && !loadingServices) fetchServicesList();
    if (activeTab === 'containers' && !loadingContainers) fetchContainersList();
  }, [activeTab, id, fetchServicesList, fetchContainersList, loadingServices, loadingContainers]);

  usePolling('detail_metrics_poll', () => fetchStatsHistory(true), 15000, activeTab === 'metrics');
  usePolling('detail_logs_poll', () => fetchNodeLogs(true), 10000, activeTab === 'logs');

  const handleRestartService = async (serviceName: string) => {
    if (!id || !isAdmin) return;
    setRestartingService(serviceName);
    try {
      await api(`/api/nodes/${id}/services/${serviceName}/restart`, { method: 'POST' });
      await fetchServicesList();
    } catch (err) {
      console.error('Service restart error:', err);
    } finally {
      setRestartingService(null);
    }
  };

  const handleRestartContainer = async (containerId: string) => {
    if (!id || !isAdmin) return;
    setRestartingContainer(containerId);
    try {
      await api(`/api/nodes/${id}/containers/${containerId}/restart`, { method: 'POST' });
      await fetchContainersList();
    } catch (err) {
      console.error('Container restart error:', err);
    } finally {
      setRestartingContainer(null);
    }
  };

  const tabs = useNodeDetailTabs({
    insightsCount: displayInsights?.length ?? 0,
    servicesCount: services?.length ?? 0,
    containersCount: containers?.length ?? 0,
  });

  if (loadingNode) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-text-3 font-interface text-xs select-none">
        <Spinner size="md" />
        <span>{t('node_detail.loading')}</span>
      </div>
    );
  }

  if (!node) {
    return (
      <div className="max-w-xl mx-auto py-20 text-center select-none space-y-4">
        <h1 className="font-serif text-2xl text-text-1">{t('node_detail.not_found_title')}</h1>
        <p className="text-text-3 text-xs">{t('node_detail.not_found_description')}</p>
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-surface hover:bg-surface-2 border border-border text-xs rounded font-interface font-bold uppercase tracking-wider text-text-2 hover:text-text-1 transition-all cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('node_detail.back_to_dashboard')}</span>
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      <NodeDetailHeader node={node} />

      <NodeDetailTabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div className="min-h-96">
        {activeTab === 'insights' && (
          <NodeDetailInsightsTab
            insights={displayInsights}
            loading={loadingInsights}
            nodeId={id}
            onRefresh={refreshInsights}
          />
        )}

        {activeTab === 'metrics' && (
          <NodeDetailMetricsTab
            statsHistory={statsHistory}
            loading={loadingStats}
            onRefresh={fetchStatsHistory}
          />
        )}

        {activeTab === 'services' && (
          <NodeDetailServicesTab
            services={services}
            loading={loadingServices}
            restartingService={restartingService}
            isAdmin={isAdmin}
            isAdminOrOperator={isAdminOrOperator}
            onRefresh={fetchServicesList}
            onRestart={handleRestartService}
          />
        )}

        {activeTab === 'containers' && (
          <NodeDetailContainersTab
            containers={containers}
            loading={loadingContainers}
            restartingContainer={restartingContainer}
            isAdmin={isAdmin}
            isAdminOrOperator={isAdminOrOperator}
            onRefresh={fetchContainersList}
            onRestart={handleRestartContainer}
          />
        )}

        {activeTab === 'logs' && (
          <NodeDetailLogsTab
            logs={logs}
            loading={loadingLogs}
            logsService={logsService}
            logsLimit={logsLimit}
            logsAutoScroll={logsAutoScroll}
            services={services}
            onServiceChange={setLogsService}
            onLimitChange={setLogsLimit}
            onAutoScrollChange={setLogsAutoScroll}
            onRefresh={fetchNodeLogs}
          />
        )}

        {activeTab === 'settings' && <NodeSettingsTab node={node} />}
      </div>
    </div>
  );
};
