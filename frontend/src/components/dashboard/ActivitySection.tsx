import React from 'react';
import { Activity } from 'lucide-react';
import { useLocale } from '../../i18n';
import { ActivityItem } from './ActivityItem';
import { formatActorName } from '../../utils/formatActor';
import type { ActivityEntry } from '../../hooks/useDashboardData';

interface ActivitySectionProps {
  entries: ActivityEntry[];
}

export const ActivitySection: React.FC<ActivitySectionProps> = ({ entries }) => {
  const { t } = useLocale();

  if (entries.length === 0) return null;

  return (
    <div className="space-y-3 relative w-full border-t border-border/30 pt-6 mt-6 animate-fade-in">
      <div className="flex items-center justify-between px-4 md:px-12">
        <div className="flex items-center gap-2">
          <Activity className="text-accent w-4.5 h-4.5" />
          <h3 className="text-sm font-bold text-text-1 tracking-wide uppercase">
            {t('swim.activity')}
          </h3>
        </div>
      </div>

      <div className="px-4 md:px-12">
        <div className="border border-border rounded-xl bg-surface divide-y divide-border overflow-hidden shadow-md">
          {entries.map((act) => (
            <ActivityItem
              key={act.id}
              action={act.action}
              actor={formatActorName(act.actor || act.user_id)}
              userId={act.user_id}
              timestamp={String(act.timestamp)}
              details={act.details}
              nodeId={act.node_id}
            />
          ))}
        </div>
      </div>
    </div>
  );
};
