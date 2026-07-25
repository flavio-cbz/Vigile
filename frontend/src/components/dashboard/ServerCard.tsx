import React, { useState } from 'react';
import { useLocale } from '../../i18n';
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
  const { t } = useLocale();
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
              title={`${topInsight.severity === 'critical' ? t('severity.critical') : topInsight.severity === 'warning' ? t('severity.attention') : t('severity.info')}: ${topInsight.headline}`}
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
            {isOnline ? t('server_card.online') : t('server_card.offline')}
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
                {topInsight.severity === 'critical' ? t('server_card.insight_critical') :
                 topInsight.severity === 'warning' ? t('server_card.insight_attention') : t('server_card.insight_info')}
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
                    {isExpanded ? t('common.less') : t('common.more')}
                  </button>
                )}
              </p>
            </div>
          ) : (
            <div className="space-y-0.5 text-left">
              <span className="text-[10px] font-extrabold font-interface tracking-wider text-severity-ok uppercase">
                {t('server_card.status')}
              </span>
              <p className="text-xs text-text-2 italic font-medium">
                {t('server_card.nominal')}
              </p>
            </div>
          )
        ) : (
          <div className="flex flex-col items-center justify-center py-1 gap-1">
            <WifiOff size={16} className="text-ink-muted animate-pulse" />
            <span className="text-xs text-severity-critical font-semibold text-center leading-tight">
               {formatOfflineDuration(node.last_heartbeat)}
            </span>
            {node.last_heartbeat && (
              <span className="text-[9px] text-ink-muted font-mono text-center">
                {(() => {
                  const d = new Date(node.last_heartbeat < 9999999999 ? node.last_heartbeat * 1000 : node.last_heartbeat);
                  const date = d.toLocaleDateString();
                  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                  return t('servers.last_contact', { time: `${date} ${time}` });
                })()}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="text-xs font-bold font-interface border-t border-border/40 pt-2 shrink-0 select-none flex justify-between items-center">
        {!isOnline ? (
          <>
            <span className="text-[9px] font-extrabold tracking-wider text-ink-muted uppercase">
              {t('server_card.network')}
            </span>
            <span className="text-severity-critical group-hover:underline">
              {t('server_card.analyze')}
            </span>
          </>
        ) : topInsight ? (
          <>
            <span className="text-[9px] font-extrabold tracking-wider text-ink-muted uppercase">
              {t('server_card.action')}
            </span>
            <span className={`group-hover:underline ${
              topInsight.severity === 'critical' ? 'text-severity-critical' :
              topInsight.severity === 'warning' ? 'text-severity-warning' : 'text-severity-info'
            }`}>
              {t('server_card.diagnose')}
            </span>
          </>
        ) : (
          <>
            <span className="text-[9px] font-extrabold tracking-wider text-ink-muted uppercase">
              {t('server_card.system')}
            </span>
            <span className="text-accent-primary group-hover:text-accent-hover transition-colors group-hover:underline">
              {t('server_card.details')}
            </span>
          </>
        )}
      </div>
    </div>
  );
};
