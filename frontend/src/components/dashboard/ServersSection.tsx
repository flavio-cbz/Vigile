import React from 'react';
import { Server as ServerIcon } from 'lucide-react';
import { useLocale } from '../../i18n';
import { SwimLane } from './SwimLane';
import { ServerCard } from './ServerCard';
import type { InsightItem } from '../../store/uiStore';
import type { Node } from '../../store/nodeStore';

interface NodeStats {
  cpu?: number;
  mem?: number;
  disk?: number;
  uptime?: number;
}

interface ServersSectionProps {
  nodes: Node[];
  bulkStatus: Record<string, NodeStats | undefined>;
  insightsByNode: Record<string, InsightItem[]>;
  hasInsightContent: boolean;
  onNodeClick: (id: string) => void;
  getTopInsight: (insights?: InsightItem[] | null) => InsightItem | null;
  formatUptime: (seconds: number | undefined) => string;
}

export const ServersSection: React.FC<ServersSectionProps> = ({
  nodes,
  bulkStatus,
  insightsByNode,
  hasInsightContent,
  onNodeClick,
  getTopInsight,
  formatUptime,
}) => {
  const { t } = useLocale();

  return (
    <SwimLane
      title={t('dash.your_servers')}
      icon={ServerIcon}
      isLoading={nodes.length === 0}
      layout="grid"
      className={hasInsightContent ? 'border-t border-border/30 pt-6 mt-6' : undefined}
    >
      {nodes.map((node) => {
        const stats = bulkStatus[node.id];
        const nodeInsights = insightsByNode[node.id];
        const topInsight = getTopInsight(nodeInsights);
        const hasFullMetrics = stats && stats.cpu !== undefined && stats.mem !== undefined && stats.disk !== undefined;
        return (
          <ServerCard
            key={node.id}
            node={node}
            metrics={
              hasFullMetrics
                ? {
                    cpu: stats.cpu ?? 0,
                    mem: stats.mem ?? 0,
                    disk: stats.disk ?? 0,
                    uptime: formatUptime(stats.uptime),
                    loading: false,
                  }
                : undefined
            }
            topInsight={topInsight}
            onClick={() => onNodeClick(node.id)}
          />
        );
      })}
    </SwimLane>
  );
};
