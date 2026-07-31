import { useLocale } from '../../i18n';
import type { NodeDetailTab } from './NodeDetailTabs';

export const useNodeDetailTabs = (params: {
  insightsCount: number;
  servicesCount: number;
  containersCount: number;
  activePlugins?: string[];
}): NodeDetailTab[] => {
  const { t } = useLocale();
  const { insightsCount, servicesCount, containersCount, activePlugins } = params;

  const tabs: NodeDetailTab[] = [
    { id: 'insights', label: t('node_detail.tab.insights'), count: insightsCount },
  ];

  if (!activePlugins || activePlugins.includes('metrics')) {
    tabs.push({ id: 'metrics', label: t('node_detail.tab.metrics') });
  }
  if (!activePlugins || activePlugins.includes('systemd')) {
    tabs.push({ id: 'services', label: t('node_detail.tab.services'), count: servicesCount });
  }
  if (!activePlugins || activePlugins.includes('docker')) {
    tabs.push({ id: 'containers', label: t('node_detail.tab.containers'), count: containersCount });
  }
  tabs.push({ id: 'logs', label: t('node_detail.tab.logs') });
  if (!activePlugins || activePlugins.includes('disk_analysis')) {
    tabs.push({ id: 'disk', label: t('node_detail.tab.disk') });
  }
  tabs.push({ id: 'settings', label: t('node_detail.tab.settings') });

  return tabs;
};
