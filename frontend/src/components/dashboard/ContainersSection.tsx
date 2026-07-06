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
  const [showAll] = useState(false);

  const filteredContainers = showAll
    ? containers
    : containers.filter((c) => !isRunning(c));

  return (
    <SwimLane
      title={t('dash.containers')}
      icon={Layers}
      subtitle={
        !showAll
          ? `${filteredContainers.length} non-stable`
          : `${containers.length} total`
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
