import React, { useState } from 'react';
import type { Node } from '../../store/nodeStore';
import type { InsightItem } from '../../store/uiStore';
import { StatusDot } from '../primitives/StatusDot';
import { InsightText } from '../primitives/InsightText';
import { MetricPill } from '../primitives/MetricPill';
import { useLocale } from '../../i18n';
import { ExternalLink, Terminal } from 'lucide-react';

interface NodeCardProps {
  node: Node;
  topInsight: InsightItem | null;
  metrics: {
    cpu_percent?: number;
    memory_percent?: number;
    disk_percent?: number;
    uptime_seconds?: number;
  } | null;
  onClick: () => void;
}

export const NodeCard: React.FC<NodeCardProps> = ({
  node,
  topInsight,
  metrics,
  onClick,
}) => {
  const { t } = useLocale();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      onClick={onClick}
      className={`card-interactive w-full max-w-sm flex flex-col justify-between group relative overflow-hidden card-accent ${isExpanded ? '!h-auto' : 'h-48'}`}
    >
      <div className="absolute top-0 right-0 w-24 h-24 bg-accent/2 pointer-events-none rounded-bl-full group-hover:bg-accent/5 transition-colors duration-200" />

      <div className="flex items-center justify-between gap-2 z-10">
        <div className="flex items-center gap-2 truncate">
          <StatusDot state={node.state} />
          <h4 className="font-interface text-sm font-bold text-text-1 group-hover:text-accent transition-colors truncate">
            {node.name}
          </h4>
        </div>
        <button className="opacity-0 group-hover:opacity-100 p-1 text-text-3 hover:text-accent rounded transition-all duration-200">
          <ExternalLink className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="my-2.5 z-10 flex-1 flex flex-col justify-center min-w-0">
        {topInsight ? (
          <div className="space-y-0.5">
            <span className="text-[10px] font-extrabold font-interface tracking-widest text-accent uppercase">
              {t('node_card.ai_insight')}
            </span>
            <InsightText size="sm" className={`block leading-snug ${isExpanded ? '' : 'line-clamp-2'}`}>
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
            </InsightText>
          </div>
        ) : (
          <div className="space-y-0.5 opacity-80">
            <span className="text-[10px] font-extrabold font-interface tracking-widest text-text-3 uppercase">
              {t('node_card.node_status')}
            </span>
            <InsightText size="sm" className="block line-clamp-1 italic text-text-2 font-normal">
              {node.online ? t('node_card.normal') : t('node_card.offline_unavailable')}
            </InsightText>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 z-10 pt-2 border-t border-border/40">
        {metrics ? (
          <MetricPill
            cpu={metrics.cpu_percent}
            mem={metrics.memory_percent}
            disk={metrics.disk_percent}
            uptime={metrics.uptime_seconds}
          />
        ) : (
          <span className="text-xs text-text-3 font-mono">
            {node.hostname || t('node_card.no_ip')}
          </span>
        )}

        <div className="flex items-center gap-1 text-[10px] font-mono text-text-3">
          <Terminal className="w-3 h-3 opacity-60" />
          <span className="uppercase">{node.arch || 'x64'}</span>
        </div>
      </div>
    </div>
  );
};
