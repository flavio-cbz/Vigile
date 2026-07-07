import { useLocale } from '../../i18n';
import type { NodeDetailTab } from './NodeDetailTabs';

export const useNodeDetailTabs = (params: {
  insightsCount: number;
  servicesCount: number;
  containersCount: number;
}): NodeDetailTab[] => {
  const { t } = useLocale();
  const { insightsCount, servicesCount, containersCount } = params;
  return [
    { id: 'insights', label: t('node_detail.tab.insights'), count: insightsCount },
    { id: 'metrics', label: t('node_detail.tab.metrics') },
    { id: 'services', label: t('node_detail.tab.services'), count: servicesCount },
    { id: 'containers', label: t('node_detail.tab.containers'), count: containersCount },
    { id: 'logs', label: t('node_detail.tab.logs') },
    { id: 'settings', label: t('node_detail.tab.settings') },
  ];
};
