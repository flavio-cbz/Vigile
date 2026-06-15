import React, { useState } from 'react';
import { Server, WifiOff, AlertTriangle } from 'lucide-react';
import type { Node } from '../../store/nodeStore';
import type { InsightItem } from '../../store/uiStore';
import { formatOfflineDuration } from '../../utils/formatTime';

interface ServerCardProps {
  node: Node;
  metrics?: {
    cpu: number;
    mem: number;
    disk: number;
    uptime: string;
    loading: boolean;
  };
  topInsight?: InsightItem | null;
  onClick: () => void;
}

export const ServerCard: React.FC<ServerCardProps> = ({ node, metrics, topInsight, onClick }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isOnline = node.online;
  const isLoading = metrics?.loading;

  let cardStatusClass = "card-success";

  if (!isOnline) {
    cardStatusClass = "card-offline";
  } else if (topInsight) {
    if (topInsight.severity === 'critical') {
      cardStatusClass = "card-critical card-pulse-critical";
    } else if (topInsight.severity === 'warning') {
      cardStatusClass = "card-warning";
    } else if (topInsight.severity === 'info') {
      cardStatusClass = "card-accent";
    }
  }

  return (
    <div
      onClick={onClick}
      className={`card-interactive card-server flex flex-col justify-between group relative overflow-hidden ${cardStatusClass} ${isExpanded ? '!h-auto' : ''}`}
    >
      <div className="flex items-center justify-between border-b border-border/40 pb-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Server size={16} className={isOnline ? 'text-accent-primary' : 'text-ink-muted'} />
          <span className="text-sm font-bold text-ink-primary truncate group-hover:text-accent-hover transition-colors" title={node.name}>
            {node.name}
          </span>
          {isOnline && topInsight && (
            <span
              className="inline-flex shrink-0 cursor-help"
              title={`${topInsight.severity === 'critical' ? 'Critique' : topInsight.severity === 'warning' ? 'Attention' : 'Info'}: ${topInsight.headline}`}
            >
              <AlertTriangle
                size={13}
                className={
                  topInsight.severity === 'critical' ? 'text-severity-critical animate-pulse' :
                  topInsight.severity === 'warning' ? 'text-severity-warning' : 'text-severity-info'
                }
              />
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span
            className={`w-2 h-2 rounded-full ${isOnline ? 'bg-success shadow-[0_0_8px_var(--color-success)]' : 'bg-ink-muted'}`}
          />
          <span className="text-xs font-medium text-ink-secondary">
            {isOnline ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      <div className="py-2 flex-1 flex flex-col justify-center min-w-0">
        {isOnline ? (
          isLoading ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-2 bg-surface-3 rounded w-1/3" />
              <div className="h-3 bg-surface-3 rounded w-full" />
            </div>
          ) : topInsight ? (
            <div className="space-y-0.5 text-left">
              <span className={`text-[10px] font-extrabold font-interface tracking-wider uppercase ${
                topInsight.severity === 'critical' ? 'text-severity-critical' :
                topInsight.severity === 'warning' ? 'text-severity-warning' : 'text-severity-info'
              }`}>
                {topInsight.severity === 'critical' ? 'Insight Critique' :
                 topInsight.severity === 'warning' ? 'Insight Attention' : 'Insight Info'}
              </span>
              <p className={`text-xs text-text-1 font-medium leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`} title={topInsight.headline}>
                {topInsight.headline}
                {topInsight.headline.length > 80 && (
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
              </p>
            </div>
          ) : (
            <div className="space-y-0.5 text-left">
              <span className="text-[10px] font-extrabold font-interface tracking-wider text-severity-ok uppercase">
                Statut
              </span>
              <p className="text-xs text-text-2 italic font-medium">
                Fonctionnement nominal
              </p>
            </div>
          )
        ) : (
          <div className="flex flex-col items-center justify-center py-1 gap-1">
            <WifiOff size={16} className="text-ink-muted animate-pulse" />
            <span className="text-xs text-severity-critical font-semibold text-center leading-tight">
              Hors-ligne depuis {formatOfflineDuration(node.last_heartbeat)}
            </span>
            {node.last_heartbeat && (
              <span className="text-[9px] text-ink-muted font-mono text-center">
                Dernier contact : {new Date(node.last_heartbeat < 9999999999 ? node.last_heartbeat * 1000 : node.last_heartbeat).toLocaleDateString('fr-FR')} à {new Date(node.last_heartbeat < 9999999999 ? node.last_heartbeat * 1000 : node.last_heartbeat).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="text-xs font-bold font-interface border-t border-border/40 pt-2 shrink-0 select-none flex justify-between items-center">
        {!isOnline ? (
          <>
            <span className="text-[9px] font-extrabold tracking-wider text-ink-muted uppercase">
              Réseau
            </span>
            <span className="text-severity-critical group-hover:underline">
              Analyser →
            </span>
          </>
        ) : topInsight ? (
          <>
            <span className="text-[9px] font-extrabold tracking-wider text-ink-muted uppercase">
              Action
            </span>
            <span className={`group-hover:underline ${
              topInsight.severity === 'critical' ? 'text-severity-critical' :
              topInsight.severity === 'warning' ? 'text-severity-warning' : 'text-severity-info'
            }`}>
              Diagnostiquer →
            </span>
          </>
        ) : (
          <>
            <span className="text-[9px] font-extrabold tracking-wider text-ink-muted uppercase">
              Système
            </span>
            <span className="text-accent-primary group-hover:text-accent-hover transition-colors group-hover:underline">
              Détails →
            </span>
          </>
        )}
      </div>
    </div>
  );
};
