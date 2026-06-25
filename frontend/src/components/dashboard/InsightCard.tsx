import React, { useState, useEffect } from 'react';
import type { InsightItem } from '../../store/uiStore';
import { useLocale } from '../../i18n';
import { InsightText } from '../primitives/InsightText';
import { SeverityTag } from '../primitives/SeverityTag';
import { Sparkles } from 'lucide-react';
import { formatOfflineDuration } from '../../utils/formatTime';

interface InsightCardProps {
  insight: InsightItem;
  nodeName: string;
  nodeId: string;
  onDiagnose: () => void;
}

export const InsightCard: React.FC<InsightCardProps> = ({
  insight,
  nodeName,
  onDiagnose,
}) => {
  const { t } = useLocale();
  const [tick, setTick] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (insight.type !== 'offline' || !insight.raw?.last_heartbeat) return;

    const interval = setInterval(() => {
      setTick((t) => t + 1);
    }, 30000);
    return () => clearInterval(interval);
  }, [insight]);

  let headline = insight.headline;
  let detail = insight.detail;
  if (insight.type === 'offline' && insight.raw?.last_heartbeat) {
    const hbTime = insight.raw.last_heartbeat;
    const durationStr = formatOfflineDuration(hbTime);
    headline = t('node_detail.offline_headline', { duration: durationStr });
    const hbLabel = new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString();
    detail = t('node_detail.offline_detail', { date: hbLabel });
  }

  let cardStatusClass = "card-accent";
  let hoverText = "group-hover:text-accent";
  let actionText = "text-accent";
  let glowColor = "bg-accent/2 group-hover:bg-accent/4";

  if (insight.severity === 'critical') {
    cardStatusClass = "card-critical card-pulse-critical";
    hoverText = "group-hover:text-severity-critical";
    actionText = "text-severity-critical";
    glowColor = "bg-severity-critical/5 group-hover:bg-severity-critical/10";
  } else if (insight.severity === 'warning') {
    cardStatusClass = "card-warning";
    hoverText = "group-hover:text-severity-warning";
    actionText = "text-severity-warning";
    glowColor = "bg-severity-warning/5 group-hover:bg-severity-warning/10";
  } else if (insight.severity === 'ok') {
    cardStatusClass = "card-success";
    hoverText = "group-hover:text-severity-ok";
    actionText = "text-severity-ok";
    glowColor = "bg-severity-ok/5 group-hover:bg-severity-ok/10";
  } else if (insight.severity === 'offline') {
    cardStatusClass = "card-offline";
    hoverText = "group-hover:text-text-2";
    actionText = "text-text-2";
    glowColor = "bg-text-3/4 group-hover:bg-text-3/8";
  }

  return (
    <div
      onClick={onDiagnose}
      data-tick={tick}
      className={`card-interactive card-insight flex flex-col justify-between group relative overflow-hidden ${cardStatusClass} ${isExpanded ? '!h-auto' : ''}`}
    >
      <div className={`absolute top-0 right-0 w-20 h-20 rounded-bl-full pointer-events-none transition-colors ${glowColor}`} />

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 z-10 shrink-0 min-w-0">
        <SeverityTag severity={insight.severity} className="whitespace-nowrap" />
        <span
          className="text-[10px] font-extrabold font-interface tracking-wider text-text-3 uppercase bg-surface-2 px-1.5 py-0.5 rounded border border-border min-w-0 break-words"
          title={nodeName}
        >
          {nodeName}
        </span>
      </div>

      <div className="my-2.5 z-10 flex-1 flex flex-col justify-center min-w-0">
        <InsightText size="sm" className={`block text-text-1 font-serif !text-[16px] md:!text-[18px] leading-snug line-clamp-2 transition-colors ${hoverText}`} title={headline}>
          {headline}
        </InsightText>
        <p className={`text-text-3 text-xs font-sans mt-1 leading-normal ${isExpanded ? '' : 'line-clamp-2'}`} title={detail}>
          {detail}
          {detail.length > 80 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1.5 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[11px]"
            >
              {isExpanded ? t('common.less') : t('common.more')}
            </button>
          )}
        </p>
      </div>

      <div className="pt-2 border-t border-border/40 flex items-center justify-between gap-2 z-10 shrink-0 min-w-0">
        <span title="Assistant IA" className="flex items-center shrink-0">
          <Sparkles className={`w-3.5 h-3.5 animate-pulse ${actionText}`} />
        </span>

        <span className={`text-xs font-bold font-interface group-hover:underline flex items-center gap-0.5 ${actionText} shrink-0 whitespace-nowrap`}>
          {t('insight_card.diagnose')}
        </span>
      </div>
    </div>
  );
};
