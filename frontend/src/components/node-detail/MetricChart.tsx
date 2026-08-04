import React from 'react';
import { Cpu, Database, Layers } from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from 'recharts';
import { MetricsTooltip } from './MetricsTooltip';
import type { StatsPoint, DiskMount, NodeBaseline, AlertRecord } from './types';

const METRIC_THEMES = {
  cpu: { stroke: '#06B6D4' },
  ram: { stroke: '#8B5CF6' },
  disk: { stroke: '#F59E0B' },
};

const ACTIVE_DOT = {
  r: 5,
  strokeWidth: 2,
  fill: 'var(--surface)',
  stroke: 'var(--accent)',
  style: { cursor: 'pointer', filter: 'drop-shadow(0 0 4px var(--accent))' },
};

const CHART_MARGIN = { top: 5, right: 5, left: -25, bottom: 5 };

const METRIC_CONFIG = {
  cpu: {
    icon: Cpu,
    iconColor: 'text-cyan-400',
    borderColor: 'bg-cyan-500/20',
    titleFr: 'HISTORIQUE CPU',
    titleEn: 'CPU HISTORICAL ACTIVITY',
    dataKey: 'cpu',
    nameFr: 'Charge CPU',
    nameEn: 'CPU Utilization',
    gradientId: 'colorCpu',
  },
  ram: {
    icon: Database,
    iconColor: 'text-purple-400',
    borderColor: 'bg-purple-500/20',
    titleFr: 'HISTORIQUE MÉMOIRE RAM',
    titleEn: 'MEMORY RAM HISTORICAL ACTIVITY',
    dataKey: 'ram',
    nameFr: 'Charge RAM',
    nameEn: 'RAM Utilization',
    gradientId: 'colorRam',
  },
  disk: {
    icon: Layers,
    iconColor: 'text-amber-400',
    borderColor: 'bg-amber-500/20',
    titleFr: 'HISTORIQUE DE STOCKAGE DES DISQUES',
    titleEn: 'DISK STORAGE HISTORY',
    dataKey: 'disk',
    nameFr: 'Disque Principal',
    nameEn: 'Main Disk',
    gradientId: 'colorDisk',
  },
} as const;

interface MetricChartProps {
  metric: 'cpu' | 'ram' | 'disk';
  mappedHistory: Array<StatsPoint & { chartIndex: number }>;
  locale: string;
  focusedMetric: 'all' | 'cpu' | 'ram' | 'disk';
  onSetFocusedMetric: (metric: 'all' | 'cpu' | 'ram' | 'disk') => void;
  getRelativeTimeLabel: (idx: number) => string;
  filteredHistory: StatsPoint[];
  diskChartData: Array<Record<string, number | string | DiskMount[]>>;
  uniqueMounts: string[];
  DISK_COLORS: string[];
  baseline?: NodeBaseline | null;
  alerts?: AlertRecord[];
  onSelectAlert?: (alert: AlertRecord) => void;
}

export const MetricChart: React.FC<MetricChartProps> = ({
  metric, mappedHistory, locale, focusedMetric,
  onSetFocusedMetric, getRelativeTimeLabel, filteredHistory,
  diskChartData, uniqueMounts, DISK_COLORS, baseline, alerts,
  onSelectAlert,
}) => {
  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const cfg = METRIC_CONFIG[metric];
  const color = METRIC_THEMES[metric].stroke;
  const Icon = cfg.icon;
  const isDisk = metric === 'disk';

  const values = mappedHistory.map((p) => (metric === 'cpu' ? p.cpu : metric === 'ram' ? p.ram : p.disk));
  const maxVal = values.length > 0 ? Math.max(...values).toFixed(1) : '0.0';
  const avgVal = values.length > 0 ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0.0';
  const firstVal = values.length > 0 ? values[0] : 0;
  const lastVal = values.length > 0 ? values[values.length - 1] : 0;
  const delta = lastVal - firstVal;
  const deltaStr = Math.abs(delta).toFixed(1);
  const trendText = delta > 1.0 ? `hausse de ${deltaStr} points` : delta < -1.0 ? `baisse de ${deltaStr} points` : 'stable';
  const secondaryPhrase = `Pic à ${maxVal}%, moyenne ${avgVal}%, ${trendText}`;

  // Large series re-animate on every 20s poll — disable animation to avoid jank.
  const isAnimationActive = mappedHistory.length <= 300;

  const curVal = lastVal;
  const mBase = baseline?.metrics?.[metric];
  const isLimited = baseline?.is_limited ?? true;

  let tierLabel = 'Normal';
  let tierBadgeClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
  let activePhrase = '';

  if (isLimited) {
    tierLabel = localT('Historique encore limité', 'Limited history');
    tierBadgeClass = 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30';
    activePhrase = `${curVal.toFixed(1)}% actuellement (seuils par défaut : alerte à 85%)`;
  } else if (mBase) {
    if (curVal >= mBase.absolute_critical || curVal >= mBase.p99) {
      tierLabel = localT('Critique absolu', 'Absolute critical');
      tierBadgeClass = 'bg-red-500/10 text-severity-critical border-red-500/30';
      activePhrase = `${curVal.toFixed(1)}% : seuil de sécurité dépassé, indépendamment de l'historique du nœud`;
    } else if (curVal >= mBase.p90) {
      tierLabel = localT('Critique relatif', 'Relative critical');
      tierBadgeClass = 'bg-amber-500/10 text-severity-warning border-amber-500/30';
      activePhrase = `Charge inhabituelle (${curVal.toFixed(1)}%), nettement au-dessus des standards de ce nœud`;
    } else if (curVal >= mBase.p75) {
      tierLabel = localT('Élevé', 'Elevated');
      tierBadgeClass = 'bg-amber-500/10 text-zone-elevated border-amber-500/30';
      activePhrase = `${curVal.toFixed(1)}% actuellement, au-dessus de l'habitude de ce nœud`;
    } else {
      tierLabel = localT('Normal', 'Normal');
      tierBadgeClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      activePhrase = `${curVal.toFixed(1)}% actuellement, dans la moyenne habituelle de ce nœud (${mBase.mean.toFixed(0)}–${mBase.p75.toFixed(0)}%)`;
    }
  }

  return (
    <div className="p-5 border border-border rounded-2xl bg-surface/30 flex flex-col gap-4 backdrop-blur-sm relative overflow-hidden">
      <div className={`absolute top-0 left-0 w-full h-[3px] ${cfg.borderColor}`} />
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <Icon className={`w-4 h-4 ${cfg.iconColor}`} />
            <span className="font-interface font-black text-xs uppercase tracking-widest text-text-1">
              {localT(cfg.titleFr, cfg.titleEn)}
            </span>
            <span className={`text-[9px] font-mono font-bold uppercase px-2 py-0.5 rounded border ${tierBadgeClass}`}>
              {tierLabel}
            </span>
          </div>
          <p className="text-xs font-interface font-bold text-text-1">
            {activePhrase}
          </p>
          <p className="text-[10px] font-mono text-text-3">
            {secondaryPhrase}
          </p>
        </div>
        {focusedMetric === metric && (
          <button
            onClick={() => onSetFocusedMetric('all')}
            className="px-2 py-1 text-[9px] font-interface font-bold border border-border hover:border-accent hover:text-accent rounded transition-all cursor-pointer self-start sm:self-auto"
          >
            {localT('RETOUR AUX AUTRES', 'BACK TO OVERVIEW')}
          </button>
        )}
      </div>

      <div className="h-60 w-full mt-2 font-mono text-[10px]">
        <ResponsiveContainer width="100%" height="100%">
          {isDisk ? (
            <AreaChart data={diskChartData} margin={CHART_MARGIN}>
              <defs>
                {uniqueMounts.length === 0 ? (
                  <linearGradient id={cfg.gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={color} stopOpacity={0.2} />
                    <stop offset="95%" stopColor={color} stopOpacity={0.0} />
                  </linearGradient>
                ) : (
                  uniqueMounts.map((mp, idx) => {
                    const c = DISK_COLORS[idx % DISK_COLORS.length];
                    const gradId = `colorDisk_${idx}`;
                    return (
                      <linearGradient key={mp} id={gradId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={c} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={c} stopOpacity={0.0} />
                      </linearGradient>
                    );
                  })
                )}
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(245, 241, 235, 0.04)" />
              <XAxis
                dataKey="chartIndex"
                tickFormatter={getRelativeTimeLabel}
                stroke="var(--text-3)"
                tickLine={false}
              />
              <YAxis stroke="var(--text-3)" tickLine={false} domain={[0, 100]} />
              <Tooltip
                wrapperStyle={{ pointerEvents: 'auto' }}
                content={<MetricsTooltip locale={locale} history={filteredHistory} alerts={alerts} onSelectAlert={onSelectAlert} />}
              />
              <ReferenceLine
                y={85}
                stroke="var(--severity-critical)"
                strokeDasharray="4 4"
                label={{
                  value: localT('Seuil Critique (85%)', 'Critical Threshold (85%)'),
                  fill: 'var(--severity-critical)',
                  fontSize: 8,
                  position: 'top',
                  style: { letterSpacing: '0.05em', fontWeight: 'bold' },
                }}
              />
              {uniqueMounts.length === 0 ? (
                <Area
                  type="monotone"
                  dataKey="Global"
                  name={localT(cfg.nameFr, cfg.nameEn)}
                  stroke={color}
                  strokeWidth={2}
                  fillOpacity={1}
                  fill={`url(#${cfg.gradientId})`}
                  activeDot={ACTIVE_DOT}
                  isAnimationActive={isAnimationActive}
                />
              ) : (
                uniqueMounts.map((mp, idx) => {
                  const c = DISK_COLORS[idx % DISK_COLORS.length];
                  const gradId = `colorDisk_${idx}`;
                  return (
                    <Area
                      key={mp}
                      type="monotone"
                      dataKey={mp}
                      name={mp}
                      stroke={c}
                      strokeWidth={2}
                      fillOpacity={1}
                      fill={`url(#${gradId})`}
                      activeDot={ACTIVE_DOT}
                      isAnimationActive={isAnimationActive}
                    />
                  );
                })
              )}
            </AreaChart>
          ) : (
            <AreaChart data={mappedHistory} margin={CHART_MARGIN}>
              <defs>
                <linearGradient id={cfg.gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={color} stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(245, 241, 235, 0.04)" />
              <XAxis
                dataKey="chartIndex"
                type="number"
                domain={[0, mappedHistory.length - 1]}
                tickFormatter={getRelativeTimeLabel}
                stroke="var(--text-3)"
                tickLine={false}
              />
              <YAxis stroke="var(--text-3)" tickLine={false} domain={[0, 100]} />
              <Tooltip
                wrapperStyle={{ pointerEvents: 'auto' }}
                content={<MetricsTooltip locale={locale} history={filteredHistory} alerts={alerts} onSelectAlert={onSelectAlert} />}
              />
              {mBase && !isLimited && (
                <>
                  <ReferenceArea y1={0} y2={mBase.p75} fill="rgba(34, 197, 94, 0.03)" />
                  <ReferenceArea y1={mBase.p75} y2={mBase.p90} fill="rgba(245, 158, 11, 0.05)" />
                  <ReferenceArea y1={mBase.p90} y2={mBase.p99} fill="rgba(245, 158, 11, 0.08)" />
                  <ReferenceArea y1={mBase.p99} y2={100} fill="rgba(239, 68, 68, 0.08)" />
                </>
              )}
              <ReferenceLine
                y={mBase?.absolute_critical || 85}
                stroke="var(--severity-critical)"
                strokeDasharray="4 4"
              />
              <Area
                type="monotone"
                dataKey={cfg.dataKey}
                name={localT(cfg.nameFr, cfg.nameEn)}
                stroke={color}
                strokeWidth={2}
                fillOpacity={1}
                fill={`url(#${cfg.gradientId})`}
                activeDot={ACTIVE_DOT}
                isAnimationActive={isAnimationActive}
              />
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
};

