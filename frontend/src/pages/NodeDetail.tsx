import React, { useCallback, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router';
import { usePolling } from '../hooks/usePolling';
import { Spinner } from '../components/primitives/Spinner';
import { api } from '../hooks/useApi';
import { usePermission } from '../hooks/usePermission';
import { useToastStore } from '../store/useToastStore';
import { usePageTitle } from '../hooks/usePageTitle';
import { useLocale } from '../i18n';
import { useNodeDetailData } from '../hooks/useNodeDetailData';
import { ArrowLeft } from 'lucide-react';
import { NodeSettingsTab } from '../components/dashboard/NodeSettingsTab';
import { NodeDetailHeader } from '../components/node-detail/NodeDetailHeader';
import { NodeDetailTabs } from '../components/node-detail/NodeDetailTabs';
import { useNodeDetailTabs } from '../components/node-detail/useNodeDetailTabs';
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

  const { canRestartDirectly, can } = usePermission();
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

  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromParams = searchParams.get('tab');
  const activeTab = tabFromParams && ['insights', 'metrics', 'services', 'containers', 'logs', 'settings'].includes(tabFromParams)
    ? (tabFromParams as NodeDetailTabId)
    : 'insights';
  const handleTabChange = useCallback(
    (tab: NodeDetailTabId) => setSearchParams({ tab }, { replace: true }),
    [setSearchParams],
  );

  useEffect(() => {
    if (activeTab === 'services' && !loadingServices) fetchServicesList();
    if (activeTab === 'containers' && !loadingContainers) fetchContainersList();
  }, [activeTab, id, fetchServicesList, fetchContainersList, loadingServices, loadingContainers]);

  usePolling('detail_metrics_poll', () => fetchStatsHistory(true), 15000, activeTab === 'metrics');
  usePolling('detail_logs_poll', () => fetchNodeLogs(true), 10000, activeTab === 'logs');

  const handleRestartService = async (serviceName: string) => {
    if (!id || !canRestartDirectly) return;
    setRestartingService(serviceName);
    try {
      const res = await api<{ error?: string | null }>(`/api/nodes/${id}/services/${serviceName}/restart`, { method: 'POST' });
      if (res?.error) {
        useToastStore.getState().addToast('error', t('chat.toast.failure'), t('node_detail.toast.service_restart_failed', { name: serviceName, error: res.error }));
      } else {
        useToastStore.getState().addToast('success', t('chat.toast.success'), t('node_detail.toast.service_restarted', { name: serviceName }));
        await fetchServicesList();
      }
    } catch (err) {
      console.error('Service restart error:', err);
    } finally {
      setRestartingService(null);
    }
  };

  const handleRestartContainer = async (containerId: string) => {
    if (!id || !canRestartDirectly) return;
    setRestartingContainer(containerId);
    const container = containers?.find(c => c.id === containerId);
    const name = container?.name || containerId;
    try {
      const res = await api<{ error?: string | null }>(`/api/nodes/${id}/containers/${containerId}/restart`, { method: 'POST' });
      if (res?.error) {
        useToastStore.getState().addToast('error', t('chat.toast.failure'), t('node_detail.toast.container_restart_failed', { name, error: res.error }));
      } else {
        useToastStore.getState().addToast('success', t('chat.toast.success'), t('node_detail.toast.container_restarted', { name }));
        await fetchContainersList();
      }
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

      <NodeDetailTabs tabs={tabs} activeTab={activeTab} onChange={handleTabChange} />

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
            isAdmin={canRestartDirectly}
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
            isAdmin={canRestartDirectly}
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
