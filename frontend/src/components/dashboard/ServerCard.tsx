import React from 'react';
import { Server, Cpu, HardDrive } from 'lucide-react';
import { useLocale } from '../../i18n';
import type { Node } from '../../store/nodeStore';

interface ServerCardProps {
  node: Node;
  metrics?: {
    cpu: number;
    mem: number;
    disk: number;
    uptime: string;
    loading: boolean;
  };
  onClick: () => void;
}

export const ServerCard: React.FC<ServerCardProps> = ({ node, metrics, onClick }) => {
  const { t } = useLocale();

  const isOnline = node.online;
  const isLoading = metrics?.loading;

  // Resource colors helper
  const getResourceColor = (val: number, type: 'cpu' | 'mem' | 'disk') => {
    const limits = {
      cpu: { warn: 40, crit: 75 },
      mem: { warn: 60, crit: 80 },
      disk: { warn: 65, crit: 85 },
    };
    const { warn, crit } = limits[type];
    if (val >= crit) return 'progress-bar-fill-danger';
    if (val >= warn) return 'progress-bar-fill-warning';
    return 'progress-bar-fill-success';
  };

  return (
    <div
      onClick={onClick}
      className="w-[260px] min-h-[160px] bg-surface-0 border border-border rounded-xl p-4 flex flex-col justify-between hover:border-border-hover hover:bg-surface-1 cursor-pointer transition-all duration-200 shadow-sm animate-fade-in group"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/40 pb-2">
        <div className="flex items-center gap-2 min-w-0">
          <Server size={16} className={isOnline ? 'text-accent-primary' : 'text-ink-muted'} />
          <span className="text-sm font-bold text-ink-primary truncate group-hover:text-accent-hover transition-colors">
            {node.name}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span
            className={`w-2 h-2 rounded-full ${isOnline ? 'bg-success shadow-[0_0_8px_var(--color-success)]' : 'bg-ink-muted'}`}
          />
          <span className="text-[10px] font-medium text-ink-secondary">
            {isOnline ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Resource Metrics */}
      <div className="space-y-2 py-2 flex-1 flex flex-col justify-center">
        {isOnline ? (
          isLoading ? (
            <div className="space-y-1.5 animate-pulse">
              <div className="h-1.5 bg-surface-2 rounded w-full" />
              <div className="h-1.5 bg-surface-2 rounded w-5/6" />
              <div className="h-1.5 bg-surface-2 rounded w-4/5" />
            </div>
          ) : (
            <div className="space-y-1.5">
              {/* CPU */}
              <div className="space-y-0.5">
                <div className="flex justify-between items-center text-[10px] font-bold">
                  <span className="text-ink-secondary flex items-center gap-1"><Cpu size={10} />{t('card.cpu')}</span>
                  <span className="font-mono text-ink-primary">{metrics?.cpu ?? 0}%</span>
                </div>
                <div className="progress-bar-track">
                  <div
                    className={`progress-bar-fill ${getResourceColor(metrics?.cpu ?? 0, 'cpu')}`}
                    style={{ width: `${metrics?.cpu ?? 0}%` }}
                  />
                </div>
              </div>

              {/* Memory */}
              <div className="space-y-0.5">
                <div className="flex justify-between items-center text-[10px] font-bold">
                  <span className="text-ink-secondary flex items-center gap-1"><Cpu size={10} />{t('card.ram')}</span>
                  <span className="font-mono text-ink-primary">{metrics?.mem ?? 0}%</span>
                </div>
                <div className="progress-bar-track">
                  <div
                    className={`progress-bar-fill ${getResourceColor(metrics?.mem ?? 0, 'mem')}`}
                    style={{ width: `${metrics?.mem ?? 0}%` }}
                  />
                </div>
              </div>

              {/* Disk */}
              <div className="space-y-0.5">
                <div className="flex justify-between items-center text-[10px] font-bold">
                  <span className="text-ink-secondary flex items-center gap-1"><HardDrive size={10} />{t('card.disk')}</span>
                  <span className="font-mono text-ink-primary">{metrics?.disk ?? 0}%</span>
                </div>
                <div className="progress-bar-track">
                  <div
                    className={`progress-bar-fill ${getResourceColor(metrics?.disk ?? 0, 'disk')}`}
                    style={{ width: `${metrics?.disk ?? 0}%` }}
                  />
                </div>
              </div>
            </div>
          )
        ) : (
          <div className="text-center text-xs text-ink-muted italic py-4">
            —
          </div>
        )}
      </div>

      {/* Footer Uptime */}
      <div className="text-[10px] font-mono text-ink-muted border-t border-border/40 pt-2 flex justify-between items-center">
        <span>Uptime</span>
        <span>{isOnline ? (metrics?.uptime || 'N/A') : 'OFFLINE'}</span>
      </div>
    </div>
  );
};
