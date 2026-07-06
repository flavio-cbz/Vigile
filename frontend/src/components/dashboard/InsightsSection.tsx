import React, { useState } from 'react';
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
  const [showStable, setShowStable] = useState(false);

  const allInsights = insights;
  const activeInsights = showStable
    ? allInsights
    : allInsights.filter((item) => item.insight.severity !== 'ok');

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

  if (activeInsights.length > 0 || allInsights.length > 0) {
    return (
      <SwimLane
        title={t('swim.insights')}
        icon={Sparkles}
        layout="grid"
        subtitle={
          stableMetricsCount > 0 && !showStable
            ? `${activeInsights.length} alerte${activeInsights.length > 1 ? 's' : ''} active${activeInsights.length > 1 ? 's' : ''}`
            : stableMetricsCount > 0
            ? `${stableMetricsCount} stable${stableMetricsCount > 1 ? 's' : ''}`
            : undefined
        }
        onSeeAll={
          stableMetricsCount > 0
            ? () => setShowStable(!showStable)
            : undefined
        }
        seeAllLabel={showStable ? 'Masquer les stables' : `Afficher les stables (${stableMetricsCount})`}
      >
        {activeInsights.map((item, idx) => (
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

  return null;
};
