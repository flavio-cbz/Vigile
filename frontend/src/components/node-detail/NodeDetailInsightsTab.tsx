import React, { useState } from 'react';
import { Sparkles, RefreshCw } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { SeverityTag } from '../primitives/SeverityTag';
import { InsightText } from '../primitives/InsightText';
import { useUiStore } from '../../store/uiStore';
import { usePolling } from '../../hooks/usePolling';
import { useLocale } from '../../i18n';
import { formatOfflineDuration } from '../../utils/formatTime';
import type { InsightRecord } from './types';

const OfflineInsightCard: React.FC<{ insight: InsightRecord; nodeId: string | undefined }> = ({ insight, nodeId }) => {
  const { t } = useLocale();
  const { openCopilot } = useUiStore();
  const [tick, setTick] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);

  usePolling(
    `offline_insight_tick_${(insight.raw as Record<string, unknown> | undefined)?.last_heartbeat ?? 'none'}`,
    () => setTick((t) => t + 1),
    30000,
    Boolean((insight.raw as Record<string, unknown> | undefined)?.last_heartbeat)
  );

  let headline = insight.headline;
  let detail = insight.detail;
  const raw = insight.raw as Record<string, unknown> | undefined;
  if (raw?.last_heartbeat) {
    const hbTime = Number(raw.last_heartbeat);
    const durationStr = formatOfflineDuration(hbTime);
    headline = t('node_detail.offline_headline', { duration: durationStr });
    const hbLabel = new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString('fr-FR');
    detail = t('node_detail.offline_detail', { date: hbLabel });
  }

  return (
    <div
      data-tick={tick}
      className={`p-5 border border-text-3/20 rounded-xl bg-surface hover:border-text-2/40 flex flex-col justify-between shadow-md transition-all group ${isExpanded ? '!h-auto' : 'h-52'}`}
      style={{ background: 'linear-gradient(135deg, rgba(92, 87, 112, 0.02), var(--surface))' }}
    >
      <div className="flex items-center justify-between gap-2 shrink-0">
        <SeverityTag severity="offline" className="whitespace-nowrap" />
        <span className="text-[8px] font-extrabold font-interface tracking-widest text-text-3 uppercase whitespace-nowrap">
          {t('node_detail.ai_report_badge')}
        </span>
      </div>

      <div className="my-2.5 flex-1 flex flex-col justify-center min-w-0">
        <InsightText size="sm" className="block text-text-1 leading-snug font-serif !text-[16px] md:!text-[17px] line-clamp-2 group-hover:text-text-2 transition-colors" title={headline}>
          {headline}
        </InsightText>
        <p className={`text-text-3 text-[10px] font-sans mt-1 leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`} title={detail}>
          {detail}
          {detail.length > 80 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[9px]"
            >
              {isExpanded ? t('common.less') : t('common.more')}
            </button>
          )}
        </p>
      </div>

      <div className="pt-2 border-t border-border/40 flex items-center justify-between shrink-0">
        <span title="Assistant IA" className="flex items-center shrink-0">
          <Sparkles className="w-3.5 h-3.5 text-text-2 animate-pulse" />
        </span>
        <button
          onClick={() =>
            openCopilot({
              trigger: 'diagnostic',
              insight,
              node_id: nodeId,
            })
          }
          className="text-[10px] font-extrabold font-interface text-text-2 hover:underline flex items-center gap-0.5 cursor-pointer"
        >
          {t('card.analyze_ai')}
        </button>
      </div>
    </div>
  );
};

const StandardInsightCard: React.FC<{ insight: InsightRecord; nodeId: string | undefined }> = ({ insight, nodeId }) => {
  const { t } = useLocale();
  const { openCopilot } = useUiStore();

  return (
    <div
      className="p-5 border border-border rounded-xl bg-surface hover:border-border-strong flex flex-col justify-between h-52 shadow-md transition-all group"
    >
      <div className="flex items-center justify-between gap-2 shrink-0">
        <SeverityTag severity={insight.severity} className="whitespace-nowrap" />
        <span className="text-[8px] font-extrabold font-interface tracking-widest text-text-3 uppercase whitespace-nowrap">
          {t('node_detail.ai_report_badge')}
        </span>
      </div>

      <div className="my-2.5 flex-1 flex flex-col justify-center min-w-0">
        <InsightText size="sm" className="block text-text-1 leading-snug font-serif !text-[16px] md:!text-[17px] line-clamp-2" title={insight.headline}>
          {insight.headline}
        </InsightText>
        <p className="text-text-3 text-[10px] font-sans mt-1 line-clamp-2 leading-relaxed" title={insight.detail}>
          {insight.detail}
        </p>
      </div>

      <div className="pt-2 border-t border-border/40 flex items-center justify-between shrink-0">
        <span title="Assistant IA" className="flex items-center shrink-0">
          <Sparkles className="w-3.5 h-3.5 text-accent animate-pulse" />
        </span>
        <button
          onClick={() =>
            openCopilot({
              trigger: 'diagnostic',
              insight,
              node_id: nodeId,
            })
          }
          className="text-[10px] font-extrabold font-interface text-accent hover:underline flex items-center gap-0.5 cursor-pointer"
        >
          {t('card.analyze_ai')}
        </button>
      </div>
    </div>
  );
};

export const NodeDetailInsightsTab: React.FC<{
  insights: InsightRecord[];
  loading: boolean;
  nodeId: string | undefined;
  onRefresh: () => void;
}> = ({ insights, loading, nodeId, onRefresh }) => {
  const { t } = useLocale();

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center px-1">
        <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-text-3">
          {t('node_detail.insights_section_title')}
        </h3>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1 rounded hover:bg-surface-2 text-text-3 hover:text-text-1 cursor-pointer transition-colors"
          title={t('node_detail.refresh_insights')}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && insights.length === 0 ? (
        <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-3">
          <Spinner size="sm" />
          <span>{t('node_detail.insights_loading')}</span>
        </div>
      ) : insights.length === 0 ? (
        <div className="py-20 border border-dashed border-border rounded-xl bg-surface/30 text-center select-none text-text-3 space-y-2 max-w-lg mx-auto">
          <Sparkles className="w-8 h-8 mx-auto text-severity-ok opacity-45" />
          <h4 className="font-interface text-xs font-bold uppercase tracking-wider text-text-2">{t('node_detail.insights_empty_title')}</h4>
          <p className="text-[10px] leading-relaxed max-w-xs mx-auto text-text-3">
            {t('node_detail.insights_empty_description')}
          </p>
        </div>
      ) : (
        <div className="grid gap-3.5 md:grid-cols-2">
          {insights.map((ins, idx) =>
            ins.type === 'offline' ? (
              <OfflineInsightCard key={idx} insight={ins} nodeId={nodeId} />
            ) : (
              <StandardInsightCard key={idx} insight={ins} nodeId={nodeId} />
            )
          )}
        </div>
      )}
    </div>
  );
};
