import React from 'react';
import { Grid3x3 } from 'lucide-react';
import { useLocale } from '../../i18n';
import { SwimLane } from './SwimLane';
import { FleetGrid, type FleetMetrics } from './FleetGrid';
import { TrendChart } from './TrendChart';
import type { InsightItem } from '../../store/uiStore';
import type { Node } from '../../store/nodeStore';

interface FleetSectionProps {
  nodes: Node[];
  bulkStatus: Record<string, FleetMetrics>;
  insightsByNode: Record<string, InsightItem[]>;
  showChart: boolean;
  onToggle: () => void;
  onNodeClick: (id: string) => void;
}

export const FleetSection: React.FC<FleetSectionProps> = ({
  nodes,
  bulkStatus,
  insightsByNode,
  showChart,
  onToggle,
  onNodeClick,
}) => {
  const { t } = useLocale();

  return (
    <>
      <SwimLane
        title={t('dash.fleet_status')}
        icon={Grid3x3}
        layout="grid"
        className="border-t border-border-strong pt-6 mt-6"
      >
        {showChart ? (
          <TrendChart nodes={nodes} />
        ) : (
          <FleetGrid
            nodes={nodes}
            bulkStatus={bulkStatus}
            insightsByNode={insightsByNode}
            onNodeClick={onNodeClick}
          />
        )}
      </SwimLane>
      <div className="flex justify-end px-4 md:px-12 -mt-4">
        <button
          type="button"
          onClick={onToggle}
          className="text-xs text-accent hover:underline font-interface font-semibold cursor-pointer transition-colors"
        >
          {showChart ? t('dash.toggle_grid') : t('dash.toggle_trends')}
        </button>
      </div>
    </>
  );
};
