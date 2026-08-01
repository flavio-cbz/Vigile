import React from 'react';
import { Sparkles, FileText, TrendingUp } from 'lucide-react';
import type { InsightItem } from '../../store/uiStore';

interface RecommendedCardProps {
  insight: InsightItem;
  nodeName?: string;
  onUnderstand: () => void;
  onPrepareProposal: () => void;
}

export const RecommendedCard: React.FC<RecommendedCardProps> = ({
  insight,
  nodeName,
  onUnderstand,
  onPrepareProposal,
}) => {
  const isCritical = insight.severity === 'critical';
  const borderClass = isCritical
    ? 'border-severity-critical/30 bg-gradient-to-br from-severity-critical/10 via-surface-1 to-surface-2'
    : 'border-severity-warning/30 bg-gradient-to-br from-severity-warning/10 via-surface-1 to-surface-2';

  const raw = insight.raw || {};
  const growthRate = raw.growth_gb_per_day ? `+${raw.growth_gb_per_day} Go/jour` : null;
  const freeGb = raw.free_gb !== undefined ? `${raw.free_gb} Go libres` : null;
  const confidenceLabel = insight.confidence === 'high'
    ? 'Confiance élevée'
    : insight.confidence === 'medium'
    ? 'Confiance moyenne'
    : null;

  return (
    <div
      className={`w-full rounded-xl border ${borderClass} p-6 shadow-xl relative overflow-hidden transition-all duration-300 animate-fade-in`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/60 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-extrabold tracking-widest font-interface uppercase px-2 py-0.5 rounded bg-accent/15 text-accent border border-accent/25">
            RECOMMANDÉ · À PLANIFIER
          </span>
          {nodeName && (
            <span className="text-[10px] font-bold font-interface text-text-2 bg-surface-2 px-2 py-0.5 rounded border border-border">
              {nodeName}
            </span>
          )}
        </div>
        {confidenceLabel && (
          <span className="text-[11px] font-mono text-text-3 flex items-center gap-1">
            <TrendingUp size={12} className="text-accent" />
            {confidenceLabel}
          </span>
        )}
      </div>

      <div className="flex items-start gap-4 mb-4">
        <div
          className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border shadow-md ${
            isCritical
              ? 'bg-severity-critical/15 border-severity-critical/30 text-severity-critical'
              : 'bg-severity-warning/15 border-severity-warning/30 text-severity-warning'
          }`}
        >
          <span className="text-2xl">{insight.icon || '⚠️'}</span>
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-bold text-text-1 tracking-tight">
            {insight.headline}
          </h3>
          <p className="text-xs text-text-2 mt-1 leading-relaxed font-sans">
            {insight.detail}
          </p>

          {(growthRate || freeGb) && (
            <div className="flex items-center flex-wrap gap-2 mt-2 text-[11px] font-mono text-text-3">
              {growthRate && <span className="bg-surface-2 px-2 py-0.5 rounded border border-border/80">{growthRate}</span>}
              {freeGb && <span className="bg-surface-2 px-2 py-0.5 rounded border border-border/80">{freeGb}</span>}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-col sm:flex-row flex-wrap items-center justify-end gap-2 sm:gap-3 pt-2 border-t border-border/40">
        <button
          onClick={onUnderstand}
          className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold font-interface uppercase tracking-wider bg-surface-2 hover:bg-surface-3 text-text-1 border border-border rounded-lg transition-colors cursor-pointer"
        >
          <Sparkles className="w-3.5 h-3.5 text-accent" />
          <span>Comprendre</span>
        </button>

        <button
          onClick={onPrepareProposal}
          className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold font-interface uppercase tracking-wider bg-accent hover:bg-accent-hover text-text-1 rounded-lg shadow-md shadow-accent/20 hover:scale-[1.02] active:scale-[0.98] transition-all cursor-pointer"
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Préparer une proposition</span>
        </button>
      </div>
    </div>
  );
};
