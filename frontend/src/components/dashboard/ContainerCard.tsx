import React, { useState } from 'react';
import { RefreshCw, Play, Square, Layers, Pause, AlertTriangle } from 'lucide-react';
import { useLocale } from '../../i18n';
import { usePermission } from '../../hooks/usePermission';
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

type ContainerState = 'running' | 'restarting' | 'paused' | 'stopped' | 'dead';

const getContainerState = (state: string): ContainerState => {
  const s = (state ?? '').toLowerCase();
  if (s === 'running') return 'running';
  if (s === 'restarting') return 'restarting';
  if (s === 'paused') return 'paused';
  if (s === 'dead' || s === 'removing') return 'dead';
  return 'stopped';  // exited, created, unknown
};

export const ContainerCard: React.FC<ContainerCardProps> = ({
  nodeId,
  nodeName,
  container,
  onRefresh,
}) => {
  const { t } = useLocale();
  const { isAdmin } = usePermission();
  const [isRestarting, setIsRestarting] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const containerState = getContainerState(container.state);

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
    switch (containerState) {
      case 'running':
        return (
          <span className="badge badge-success flex items-center gap-1">
            <Play size={8} className="fill-current" />
            EN COURS
          </span>
        );
      case 'restarting':
        return (
          <span className="badge badge-warning flex items-center gap-1">
            <RefreshCw size={8} className="animate-spin" />
            REDÉMARRAGE
          </span>
        );
      case 'paused':
        return (
          <span className="badge badge-warning flex items-center gap-1">
            <Pause size={8} className="fill-current" />
            EN PAUSE
          </span>
        );
      case 'dead':
        return (
          <span className="badge badge-danger flex items-center gap-1 animate-pulse">
            <AlertTriangle size={8} />
            DÉFAILLANT
          </span>
        );
      case 'stopped':
      default:
        return (
          <span className="badge badge-subtle flex items-center gap-1">
            <Square size={8} className="fill-current" />
            ARRÊTÉ
          </span>
        );
    }
  };

  const isRestartDisabled = isRestarting || containerState === 'dead' || containerState === 'restarting';

  // Highlight container cards according to their execution state
  let cardStatusClass = "card-success";

  if (containerState === 'dead') {
    cardStatusClass = "card-critical card-pulse-critical";
  } else if (containerState === 'restarting' || containerState === 'paused') {
    cardStatusClass = "card-warning";
  } else if (containerState === 'stopped') {
    cardStatusClass = "card-offline";
  }

  return (
    <div
      className={`card card-container flex flex-col justify-between group relative overflow-hidden ${cardStatusClass} ${isExpanded ? '!h-auto' : ''}`}
    >
      {/* Top Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="text-sm font-bold text-ink-primary truncate group-hover:text-accent-hover transition-colors" title={container.name}>
            {container.name}
          </h4>
          <span className="text-xs text-ink-muted flex items-center gap-1 font-mono uppercase truncate mt-0.5" title={nodeName}>
            <Layers size={12} />
            {nodeName}
          </span>
        </div>
        <div className="shrink-0">{getStatusBadge()}</div>
      </div>

      {/* Info details */}
      <div className="my-2 min-w-0">
        <div className={`text-xs text-ink-secondary ${isExpanded ? 'break-all whitespace-normal' : 'truncate'}`} title={container.image}>
          Image: {container.image}
          {container.image.length > 30 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[10px]"
            >
              {isExpanded ? 'Moins' : 'Plus'}
            </button>
          )}
        </div>
        <div className={`text-xs text-ink-muted font-mono mt-1 ${isExpanded ? 'break-all whitespace-normal' : 'truncate'}`} title={container.status}>
          {container.status}
        </div>
      </div>

      {/* Admin actions footer */}
      <div className="border-t border-border/40 pt-2 flex items-center justify-between mt-auto">
        <span className="text-xs text-ink-muted truncate font-mono">
          ID: {container.id.substring(0, 12)}
        </span>
        {isAdmin && (
          <button
            onClick={handleRestart}
            disabled={isRestartDisabled}
            className="btn btn-secondary text-xs py-1 px-2 border-border/50 text-ink-secondary hover:text-ink-primary flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
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
