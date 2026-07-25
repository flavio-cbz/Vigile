import React, { useState } from 'react';
import { Layers } from 'lucide-react';
import { useLocale } from '../../i18n';
import { SwimLane } from './SwimLane';
import { ContainerCard } from './ContainerCard';
import type { ContainerItem } from '../../hooks/useDashboardData';

interface ContainersSectionProps {
  containers: ContainerItem[];
  isLoading: boolean;
  onRefresh: () => void;
}

const isRunning = (c: ContainerItem): boolean => {
  const state = (c.state ?? '').toLowerCase();
  const status = (c.status ?? '').toLowerCase();
  return state === 'running' || status.includes('up');
};

export const ContainersSection: React.FC<ContainersSectionProps> = ({
  containers,
  isLoading,
  onRefresh,
}) => {
  const { t } = useLocale();
  const [showAll, setShowAll] = useState(false);

  const filteredContainers = showAll
    ? containers
    : containers.filter((c) => !isRunning(c));

  return (
    <SwimLane
      title={t('dash.containers')}
      icon={Layers}
      subtitle={
        <span className="flex items-center gap-2">
          <span>
            {!showAll
              ? `${filteredContainers.length} non-stable`
              : `${containers.length} total`}
          </span>
          <button
            onClick={() => setShowAll((v) => !v)}
            className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider border border-border-strong/20 rounded text-text-2 hover:text-text-1 hover:border-accent/30 transition-colors cursor-pointer"
          >
            {showAll ? 'Failed only' : 'Show all'}
          </button>
        </span>
      }
      isLoading={isLoading && containers.length === 0}
      className="border-t border-border/30 pt-6 mt-6"
    >
      {filteredContainers.map((container) => (
        <ContainerCard
          key={`${container.nodeId}-${container.id}`}
          nodeId={container.nodeId}
          nodeName={container.nodeName}
          container={container}
          onRefresh={onRefresh}
        />
      ))}
    </SwimLane>
  );
};
