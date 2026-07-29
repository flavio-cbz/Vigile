import React from 'react';
import { Cpu, Database, Layers } from 'lucide-react';
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { MetricsTooltip } from './MetricsTooltip';
import type { StatsPoint, DiskMount } from './types';

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
  chartStyle: 'area' | 'line';
  locale: string;
  focusedMetric: 'all' | 'cpu' | 'ram' | 'disk';
  onSetFocusedMetric: (metric: 'all' | 'cpu' | 'ram' | 'disk') => void;
  getRelativeTimeLabel: (idx: number) => string;
  filteredHistory: StatsPoint[];
  diskChartData: Array<Record<string, number | string | DiskMount[]>>;
  uniqueMounts: string[];
  DISK_COLORS: string[];
}

export const MetricChart: React.FC<MetricChartProps> = ({
  metric, mappedHistory, chartStyle, locale, focusedMetric,
  onSetFocusedMetric, getRelativeTimeLabel, filteredHistory,
  diskChartData, uniqueMounts, DISK_COLORS,
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
  const summaryPhrase = `Pic à ${maxVal}%, moyenne ${avgVal}%, ${trendText}`;

  return (
    <div className="p-5 border border-border rounded-2xl bg-surface/30 flex flex-col gap-4 backdrop-blur-sm relative overflow-hidden">
      <div className={`absolute top-0 left-0 w-full h-[3px] ${cfg.borderColor}`} />
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <Icon className={`w-4 h-4 ${cfg.iconColor}`} />
            <span className="font-interface font-black text-xs uppercase tracking-widest text-text-1">
              {localT(cfg.titleFr, cfg.titleEn)}
            </span>
          </div>
          <p className="text-[11px] font-mono text-text-3 mt-1">
            {summaryPhrase}
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
            <LineChart data={diskChartData} margin={CHART_MARGIN}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(245, 241, 235, 0.04)" />
              <XAxis
                dataKey="chartIndex"
                tickFormatter={getRelativeTimeLabel}
                stroke="var(--text-3)"
                tickLine={false}
              />
              <YAxis stroke="var(--text-3)" tickLine={false} domain={[0, 100]} />
              <Tooltip content={<MetricsTooltip locale={locale} history={filteredHistory} />} />
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
                <Line
                  type="monotone"
                  dataKey="Global"
                  name={localT(cfg.nameFr, cfg.nameEn)}
                  stroke={color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={ACTIVE_DOT}
                />
              ) : (
                uniqueMounts.map((mp, idx) => (
                  <Line
                    key={mp}
                    type="monotone"
                    dataKey={mp}
                    name={mp}
                    stroke={DISK_COLORS[idx % DISK_COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                    activeDot={ACTIVE_DOT}
                  />
                ))
              )}
            </LineChart>
          ) : chartStyle === 'area' ? (
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
              <Tooltip content={<MetricsTooltip locale={locale} history={filteredHistory} />} />
              <Area
                type="monotone"
                dataKey={cfg.dataKey}
                name={localT(cfg.nameFr, cfg.nameEn)}
                stroke={color}
                strokeWidth={2}
                fillOpacity={1}
                fill={`url(#${cfg.gradientId})`}
                activeDot={ACTIVE_DOT}
              />
            </AreaChart>
          ) : (
            <LineChart data={mappedHistory} margin={CHART_MARGIN}>
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
              <Tooltip content={<MetricsTooltip locale={locale} history={filteredHistory} />} />
              <Line
                type="monotone"
                dataKey={cfg.dataKey}
                name={localT(cfg.nameFr, cfg.nameEn)}
                stroke={color}
                strokeWidth={2}
                dot={false}
                activeDot={ACTIVE_DOT}
              />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
};
