import React from 'react';
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

export const ContainersSection: React.FC<ContainersSectionProps> = ({
  containers,
  isLoading,
  onRefresh,
}) => {
  const { t } = useLocale();

  return (
    <SwimLane
      title={t('dash.containers')}
      icon={Layers}
      isLoading={isLoading && containers.length === 0}
      className="border-t border-border/30 pt-6 mt-6"
    >
      {containers.map((container) => (
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
