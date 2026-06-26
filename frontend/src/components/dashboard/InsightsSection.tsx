import React from 'react';
import { Sparkles } from 'lucide-react';
import { useLocale } from '../../i18n';
import { SwimLane } from './SwimLane';
import { InsightCard } from './InsightCard';
import type { InsightItem } from '../../store/uiStore';

interface InsightsSectionProps {
  loading: boolean;
  insights: Array<{ insight: InsightItem; nodeName: string; nodeId: string }>;
  stableMetricsCount: number;
  onDiagnose: (insight: InsightItem, nodeId: string) => void;
}

export const InsightsSection: React.FC<InsightsSectionProps> = ({
  loading,
  insights,
  stableMetricsCount,
  onDiagnose,
}) => {
  const { t } = useLocale();

  if (loading) {
    return (
      <SwimLane title={t('swim.insights')} icon={Sparkles} layout="grid">
        {[1, 2, 3].map((i) => (
          <div key={i} className="card card-insight animate-pulse flex flex-col justify-between">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div className="h-4 w-16 bg-surface-2 rounded" />
              <div className="h-4 w-20 bg-surface-2 rounded" />
            </div>
            <div className="space-y-2">
              <div className="h-5 bg-surface-2 rounded w-full" />
              <div className="h-5 bg-surface-2 rounded w-4/5" />
              <div className="h-3 bg-surface-2 rounded w-3/5 mt-2" />
            </div>
          </div>
        ))}
      </SwimLane>
    );
  }

  if (insights.length > 0) {
    return (
      <SwimLane
        title={t('swim.insights')}
        icon={Sparkles}
        layout="grid"
        subtitle={
          stableMetricsCount > 0
            ? `• ${stableMetricsCount} métrique${stableMetricsCount > 1 ? 's' : ''} stable${stableMetricsCount > 1 ? 's' : ''} sur la flotte`
            : undefined
        }
      >
        {insights.map((item, idx) => (
          <InsightCard
            key={`${item.nodeId}-${item.insight.type}-${idx}`}
            insight={item.insight}
            nodeName={item.nodeName}
            nodeId={item.nodeId}
            onDiagnose={() => onDiagnose(item.insight, item.nodeId)}
          />
        ))}
      </SwimLane>
    );
  }

  if (stableMetricsCount > 0) {
    return (
      <div className="px-4 md:px-12">
        <div className="flex items-center gap-2 text-xs text-success bg-success/5 border border-success/15 rounded-lg py-2.5 px-4 w-fit">
          <span className="text-sm">✓</span>
          <span className="font-interface font-medium">
            {t('dash.stable_metrics', { count: stableMetricsCount })}
          </span>
        </div>
      </div>
    );
  }

  return null;
};
