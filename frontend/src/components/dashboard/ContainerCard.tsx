import React, { useState } from 'react';
import { RefreshCw, Play, Square, Layers } from 'lucide-react';
import { useLocale } from '../../i18n';
import { useAuthStore } from '../../store/authStore';
import { useToastStore } from '../../store/useToastStore';
import { api } from '../../hooks/useApi';

interface Container {
  id: string;
  name: string;
  image: string;
  state: string;  // e.g. "running", "exited"
  status: string; // e.g. "Up 2 hours", "Exited (0) 5 minutes ago"
}

interface ContainerCardProps {
  nodeId: string;
  nodeName: string;
  container: Container;
  onRefresh?: () => void;
}

export const ContainerCard: React.FC<ContainerCardProps> = ({
  nodeId,
  nodeName,
  container,
  onRefresh,
}) => {
  const { t } = useLocale();
  const user = useAuthStore((s) => s.user);
  const [isRestarting, setIsRestarting] = useState(false);

  const isAdmin = user?.role === 'admin';
  const isRunning = container.state.toLowerCase() === 'running' || container.status.toLowerCase().includes('up');

  const handleRestart = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isRestarting) return;
    setIsRestarting(true);
    try {
      await api<{ success: boolean; output: string }>(
        `/api/nodes/${nodeId}/containers/${container.id}/restart`,
        { method: 'POST' }
      );
      useToastStore.getState().addToast(
        'success',
        'Succès',
        t('card.restarting') + ' ' + container.name
      );
      if (onRefresh) onRefresh();
    } catch (err: any) {
      useToastStore.getState().addToast(
        'error',
        'Erreur',
        err.message || 'Impossible de redémarrer le conteneur.'
      );
    } finally {
      setIsRestarting(false);
    }
  };

  const getStatusBadge = () => {
    if (isRunning) {
      return (
        <span className="badge badge-success flex items-center gap-1">
          <Play size={8} className="fill-current" />
          {t('card.status.running')}
        </span>
      );
    }
    return (
      <span className="badge badge-danger flex items-center gap-1">
        <Square size={8} className="fill-current" />
        {t('card.status.stopped')}
      </span>
    );
  };

  return (
    <div className="w-[260px] min-h-[125px] bg-surface-0 border border-border rounded-xl p-4 flex flex-col justify-between hover:border-border-hover hover:bg-surface-1 transition-all duration-200 shadow-sm animate-fade-in group">
      {/* Top Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="text-sm font-bold text-ink-primary truncate group-hover:text-accent-hover transition-colors" title={container.name}>
            {container.name}
          </h4>
          <span className="text-[10px] text-ink-muted flex items-center gap-1 font-mono uppercase truncate mt-0.5" title={nodeName}>
            <Layers size={10} />
            {nodeName}
          </span>
        </div>
        <div className="shrink-0">{getStatusBadge()}</div>
      </div>

      {/* Info details */}
      <div className="my-2 min-w-0">
        <div className="text-[10px] text-ink-secondary truncate" title={container.image}>
          Image: {container.image}
        </div>
        <div className="text-[9px] text-ink-muted font-mono mt-1 truncate">
          {container.status}
        </div>
      </div>

      {/* Admin actions footer */}
      <div className="border-t border-border/40 pt-2 flex items-center justify-between mt-auto">
        <span className="text-[9px] text-ink-muted truncate font-mono">
          ID: {container.id.substring(0, 12)}
        </span>
        {isAdmin && (
          <button
            onClick={handleRestart}
            disabled={isRestarting}
            className="btn btn-secondary text-[10px] py-1 px-2 border-border/50 text-ink-secondary hover:text-ink-primary flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            aria-label="Restart container"
          >
            <RefreshCw size={10} className={isRestarting ? 'animate-spin text-accent-primary' : ''} />
            {isRestarting ? t('card.restarting') : t('card.restart')}
          </button>
        )}
      </div>
    </div>
  );
};
