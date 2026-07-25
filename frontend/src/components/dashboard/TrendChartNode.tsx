import React from 'react';
import { Cpu } from 'lucide-react';
import { TrendBar } from './TrendBar';
import type { BarData } from './TrendBar';
import { PeriodSelector } from './PeriodSelector';
import type { Node } from '../../store/nodeStore';
import { useLocale } from '../../i18n';
import type { IncidentPeriod } from './trendDataUtils';

interface TrendChartNodeProps {
  node: Node;
  timelineBars: BarData[];
  uptimePct: string;
  nodeIncidents: IncidentPeriod[];
  hoveredBar: { nodeIdx: number; barIdx: number } | null;
  onBarHover: (nodeIdx: number, barIdx: number) => void;
  nodeIdx: number;
}

export const TrendChartNode: React.FC<TrendChartNodeProps> = ({
  node,
  timelineBars,
  uptimePct,
  nodeIncidents,
  hoveredBar,
  onBarHover,
  nodeIdx,
}) => {
  const { t } = useLocale();

  return (
    <div className="flex flex-col gap-2.5 p-4 rounded-xl border border-border bg-surface/40 hover:border-border-strong hover:bg-surface-2/10 transition-all duration-300">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${
              node.online
                ? 'bg-severity-ok shadow-[0_0_8px_var(--severity-ok)]'
                : 'bg-severity-critical shadow-[0_0_8px_var(--severity-critical)] animate-pulse'
            }`}
          />
          <span className="font-bold text-xs text-text-1">{node.name}</span>
          <span className="text-[10px] text-text-3 font-mono truncate max-w-[120px] sm:max-w-none">
            {node.hostname || t('trend.no_hostname')}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold text-text-3 uppercase tracking-wider">{t('trend.uptime_label')}</span>
          <span className={`text-xs font-mono font-bold ${
            uptimePct === '100.0%' || uptimePct === '100%'
              ? 'text-severity-ok'
              : uptimePct.startsWith('99')
              ? 'text-severity-warning'
              : 'text-severity-critical'
          }`}>
            {uptimePct}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-1 py-1.5">
          {timelineBars.map((bar, barIdx) => (
            <TrendBar
              key={barIdx}
              bar={bar}
              barIdx={barIdx}
              isHovered={hoveredBar?.nodeIdx === nodeIdx && hoveredBar?.barIdx === barIdx}
              onHover={() => onBarHover(nodeIdx, barIdx)}
              onLeave={() => onBarHover(-1, -1)}
            />
          ))}
        </div>

        <div className="flex items-center justify-between text-[9px] text-text-3 font-semibold uppercase tracking-wider">
          <span>{t('trend.timeline_24h')}</span>
          <span className="w-12 h-[1px] bg-border-strong/40 flex-1 mx-2" />
          <span>{t('trend.timeline_now')}</span>
        </div>
      </div>

      <div className="mt-1 text-[10px] border-t border-border/20 pt-2">
        {nodeIncidents.length === 0 ? (
          <div className="flex items-center gap-1.5 text-severity-ok font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-severity-ok shrink-0" />
            <span>{t('trend.all_clear')}</span>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5 text-severity-warning font-bold uppercase tracking-wider text-[9px]">
              <span>{t('trend.incident_log', { count: nodeIncidents.length })}</span>
            </div>
            <div className="flex flex-col gap-1 max-h-24 overflow-y-auto pr-1">
              {nodeIncidents.map((inc, incIdx) => {
                const isCrit = inc.type === 'critical';
                return (
                  <div key={incIdx} className="flex items-start justify-between gap-4 py-1 px-2.5 rounded bg-surface-3/20 border border-border/30">
                    <div className="flex items-center gap-2">
                      <span className={`w-1 h-1 rounded-full shrink-0 ${isCrit ? 'bg-severity-critical animate-pulse' : 'bg-severity-warning'}`} />
                      <span className={isCrit ? 'text-severity-critical font-bold' : 'text-severity-warning font-bold'}>
                        {isCrit ? t('trend.outage') : t('trend.alert')}
                      </span>
                      <span className="text-text-2">— {inc.details}</span>
                    </div>
                    <span className="text-text-3 font-mono text-[9px] whitespace-nowrap">
                      {inc.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
