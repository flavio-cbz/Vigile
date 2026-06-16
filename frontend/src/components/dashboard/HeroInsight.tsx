import React from 'react';
import { InsightText } from '../primitives/InsightText';
import { SeverityTag } from '../primitives/SeverityTag';
import { Sparkles, ShieldCheck } from 'lucide-react';
import type { InsightItem } from '../../store/uiStore';

interface HeroInsightProps {
  insight: InsightItem | null; // null = "all clear"
  nodeName?: string;
  onDiagnose: () => void;
  connectedCount: number;
}

export const HeroInsight: React.FC<HeroInsightProps> = ({
  insight,
  nodeName,
  onDiagnose,
  connectedCount,
}) => {
  if (!insight) {
    return (
      <div className="w-full relative overflow-hidden rounded-xl border border-severity-ok/20 bg-gradient-to-br from-severity-ok/5 to-bg p-6 md:p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-lg select-none">
        <div className="absolute -right-20 -bottom-20 w-60 h-60 bg-severity-ok/10 rounded-full filter blur-3xl pointer-events-none" />

        <div className="flex items-center gap-4 z-10">
          <div className="w-12 h-12 rounded-xl bg-severity-ok/15 border border-severity-ok/25 flex items-center justify-center shadow-md">
            <ShieldCheck className="w-6 h-6 text-severity-ok" />
          </div>
          <div>
            <SeverityTag severity="ok" />
            <div className="mt-1">
              <InsightText className="text-text-1">
                {connectedCount} machine{connectedCount > 1 ? 's' : ''} connectée{connectedCount > 1 ? 's' : ''} — tout est calme
              </InsightText>
            </div>
            <p className="text-text-2 text-xs font-medium font-sans mt-0.5">
              Aucune anomalie détectée sur votre homelab. Vigile veille sur votre infrastructure.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const isCritical = insight.severity === 'critical';
  const borderClass = isCritical ? 'border-severity-critical/20 bg-gradient-to-br from-severity-critical/5 to-bg' : 'border-severity-warning/20 bg-gradient-to-br from-severity-warning/5 to-bg';
  const glowBgClass = isCritical ? 'bg-severity-critical/10' : 'bg-severity-warning/10';

  return (
    <div className={`w-full relative overflow-hidden rounded-xl border p-6 md:p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-lg ${borderClass}`}>
      <div className={`absolute -right-20 -bottom-20 w-60 h-60 rounded-full filter blur-3xl pointer-events-none ${glowBgClass}`} />

      <div className="flex items-start md:items-center gap-4 z-10 flex-1 min-w-0">
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center shadow-md border ${
          isCritical
            ? 'bg-severity-critical/15 border-severity-critical/25 text-severity-critical'
            : 'bg-severity-warning/15 border-severity-warning/25 text-severity-warning'
        }`}>
          <span className="text-xl">{insight.icon || '⚠️'}</span>
        </div>
        <div className="flex-1 min-w-0">
          <SeverityTag severity={insight.severity} />
          {nodeName && (
            <span className="ml-2 text-[10px] font-bold font-interface text-text-3 uppercase tracking-wider bg-surface-2 px-1.5 py-0.5 rounded border border-border">
              {nodeName}
            </span>
          )}
          <div className="mt-1">
            <InsightText size="md" className="block text-text-1">
              {insight.headline}
            </InsightText>
          </div>
          <p className="text-text-2 text-xs font-sans mt-0.5 truncate leading-relaxed">
            {insight.detail}
          </p>
        </div>
      </div>

      <div className="z-10 shrink-0 self-end md:self-center">
        <button
          onClick={onDiagnose}
          className="flex items-center gap-2 px-4 py-2 text-xs font-bold font-interface tracking-wider uppercase bg-accent hover:bg-accent-hover text-text-1 rounded shadow-lg shadow-accent/20 cursor-pointer hover:shadow-accent/30 hover:scale-[1.02] active:scale-[0.98] transition-all duration-200"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Diagnostiquer</span>
        </button>
      </div>
    </div>
  );
};
