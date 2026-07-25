import React, { useMemo, useState } from 'react';
import {
  Cpu,
  Database,
  Layers,
  Activity,
  RefreshCw,
} from 'lucide-react';
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
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { StatsPoint, DiskMount } from './types';
import { MetricsTooltip } from './MetricsTooltip';
import { MetricsOverviewCards } from './MetricsOverviewCards';
import { DiskMountCards } from './DiskMountCards';

const METRIC_THEMES = {
  cpu: { stroke: '#06B6D4' },
  ram: { stroke: '#8B5CF6' },
  disk: { stroke: '#F59E0B' },
};

function generateSparklinePaths(points: number[], width = 120, height = 32, padding = 2) {
  if (points.length < 2) return { line: '', area: '' };
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min === 0 ? 1 : max - min;

  const coords = points.map((val, index) => {
    const x = (index / (points.length - 1)) * (width - padding * 2) + padding;
    const y = height - ((val - min) / range) * (height - padding * 2) - padding;
    return { x, y };
  });

  const linePath = `M ${coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' L ')}`;
  const areaPath = `${linePath} L ${coords[coords.length - 1].x.toFixed(1)},${height.toFixed(1)} L ${coords[0].x.toFixed(1)},${height.toFixed(1)} Z`;

  return { line: linePath, area: areaPath };
}

export const NodeDetailMetricsTab: React.FC<{
  statsHistory: StatsPoint[];
  loading: boolean;
  onRefresh: () => void;
}> = ({ statsHistory, loading, onRefresh }) => {
  const { locale, t } = useLocale();
  const [timeRange, setTimeRange] = useState<'30m' | '12h' | '24h'>('30m');
  const [chartStyle, setChartStyle] = useState<'area' | 'line'>('area');
  const [focusedMetric, setFocusedMetric] = useState<'all' | 'cpu' | 'ram' | 'disk'>('all');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const lastRefreshed = useMemo(
    () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    [statsHistory],
  );

  const handleRefreshClick = () => {
    setIsRefreshing(true);
    onRefresh();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  const is30mAvailable = statsHistory.length >= 30;
  const is12hAvailable = statsHistory.length >= 720;
  const is24hAvailable = statsHistory.length >= 1440;

  const filteredHistory = useMemo(() => {
    if (timeRange === '30m' && statsHistory.length >= 30) return statsHistory.slice(-30);
    if (timeRange === '12h' && statsHistory.length >= 720) return statsHistory.slice(-720);
    if (timeRange === '24h' && statsHistory.length >= 1440) return statsHistory.slice(-1440);
    return statsHistory;
  }, [statsHistory, timeRange]);

  const mappedHistory = useMemo(() => {
    return filteredHistory.map((point, idx) => ({
      ...point,
      chartIndex: idx,
    }));
  }, [filteredHistory]);

  const lastSnap = statsHistory[statsHistory.length - 1];
  const disks = lastSnap?.disks || [];

  const cpuHistory = useMemo(() => statsHistory.map(p => p.cpu), [statsHistory]);
  const ramHistory = useMemo(() => statsHistory.map(p => p.ram), [statsHistory]);
  const diskHistory = useMemo(() => statsHistory.map(p => p.disk), [statsHistory]);

  const uniqueMounts = useMemo(() => {
    const set = new Set<string>();
    statsHistory.forEach(point => {
      if (point.disks) {
        point.disks.forEach(d => set.add(d.mount_point));
      }
    });
    return Array.from(set);
  }, [statsHistory]);

  const DISK_COLORS = ['#f59e0b', '#10b981', '#3b82f6', '#ec4899', '#8b5cf6', '#06b6d4'];

  const diskChartData = useMemo(() => {
    return filteredHistory.map((point, idx) => {
      const dataPoint: Record<string, number | string | DiskMount[]> = {
        ...point,
        chartIndex: idx,
      };
      if (point.disks && point.disks.length > 0) {
        point.disks.forEach(d => {
          dataPoint[d.mount_point] = d.percent;
        });
      } else {
        dataPoint["Global"] = point.disk;
      }
      return dataPoint;
    });
  }, [filteredHistory]);

  const cpuTrend = useMemo(() => {
    if (cpuHistory.length < 5) return { dir: 'flat', val: 0 };
    const firstAvg = cpuHistory.slice(0, 5).reduce((a, b) => a + b, 0) / 5;
    const lastAvg = cpuHistory.slice(-5).reduce((a, b) => a + b, 0) / 5;
    const diff = lastAvg - firstAvg;
    return { dir: diff > 0.5 ? 'up' : diff < -0.5 ? 'down' : 'flat', val: Math.abs(diff) };
  }, [cpuHistory]);

  const ramTrend = useMemo(() => {
    if (ramHistory.length < 5) return { dir: 'flat', val: 0 };
    const firstAvg = ramHistory.slice(0, 5).reduce((a, b) => a + b, 0) / 5;
    const lastAvg = ramHistory.slice(-5).reduce((a, b) => a + b, 0) / 5;
    const diff = lastAvg - firstAvg;
    return { dir: diff > 0.5 ? 'up' : diff < -0.5 ? 'down' : 'flat', val: Math.abs(diff) };
  }, [ramHistory]);

  const diskTrend = useMemo(() => {
    if (diskHistory.length < 5) return { dir: 'flat', val: 0 };
    const firstAvg = diskHistory.slice(0, 5).reduce((a, b) => a + b, 0) / 5;
    const lastAvg = diskHistory.slice(-5).reduce((a, b) => a + b, 0) / 5;
    const diff = lastAvg - firstAvg;
    return { dir: diff > 0.1 ? 'up' : diff < -0.1 ? 'down' : 'flat', val: Math.abs(diff) };
  }, [diskHistory]);

  const cpuSpark = useMemo(() => generateSparklinePaths(cpuHistory.slice(-15)), [cpuHistory]);
  const ramSpark = useMemo(() => generateSparklinePaths(ramHistory.slice(-15)), [ramHistory]);
  const diskSpark = useMemo(() => generateSparklinePaths(diskHistory.slice(-15)), [diskHistory]);

  const getStatus = (val: number, type: 'cpu' | 'ram' | 'disk') => {
    const limits = type === 'disk' ? { warn: 70, crit: 85 } : { warn: 50, crit: 80 };
    if (val >= limits.crit) return { text: localT('Critique', 'Critical'), bg: 'bg-red-500/10 text-severity-critical border-red-500/20' };
    if (val >= limits.warn) return { text: localT('Avertissement', 'Warning'), bg: 'bg-amber-500/10 text-severity-warning border-amber-500/20' };
    return { text: localT('Nominal', 'Nominal'), bg: 'bg-emerald-500/10 text-severity-ok border-emerald-500/20' };
  };

  const getRelativeTimeLabel = (idx: number) => {
    const diff = idx - (filteredHistory.length - 1);
    if (diff === 0) return localT('Maintenant', 'Now');
    return `${diff}m`;
  };

  const handleToggleMetric = (metric: 'cpu' | 'ram' | 'disk') => {
    setFocusedMetric(prev => prev === metric ? 'all' : metric);
  };

  if (loading && statsHistory.length === 0) {
    return (
      <div className="py-24 text-center text-text-3 flex flex-col items-center justify-center gap-3">
        <Spinner size="md" />
        <span className="font-interface text-xs uppercase tracking-widest text-accent animate-pulse">
          {t('node_detail.metrics_loading')}
        </span>
      </div>
    );
  }

  if (statsHistory.length === 0) {
    return (
      <div className="py-24 border border-dashed border-border rounded-2xl bg-surface/40 text-center text-text-3 flex flex-col items-center justify-center gap-2">
        <Activity className="w-8 h-8 text-text-3 opacity-40" />
        <span className="font-interface text-xs font-semibold">{t('node_detail.metrics_empty')}</span>
      </div>
    );
  }

  const timeRanges = [
    { id: '30m', label: localT('30 min', '30 min'), available: is30mAvailable },
    { id: '12h', label: localT('12h', '12h'), available: is12hAvailable },
    { id: '24h', label: localT('24h', '24h'), available: is24hAvailable },
  ] as const;

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/80 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-interface font-extrabold uppercase tracking-wider text-text-1">
              {localT('Moniteur de Télémétrie', 'Telemetry Monitor')}
            </h3>
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
          </div>
          <p className="text-[10px] text-text-3 font-medium">
            {localT('Dernière synchronisation :', 'Last synchronization :')} {lastRefreshed}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex bg-surface-2 p-1 rounded-lg border border-border">
            {timeRanges.map((r) => {
              const isSelected = timeRange === r.id;
              if (!r.available) {
                return (
                  <button
                    key={r.id}
                    disabled
                    className="px-2.5 py-1 text-[10px] font-interface font-bold uppercase rounded opacity-35 cursor-not-allowed text-text-3 border border-dashed border-border"
                    title={localT('Données historiques insuffisantes pour cette période', 'Insufficient data')}
                  >
                    {r.label}
                  </button>
                );
              }
              return (
                <button
                  key={r.id}
                  onClick={() => setTimeRange(r.id)}
                  className={`px-2.5 py-1 text-[10px] font-interface font-bold uppercase rounded transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-accent text-bg shadow'
                      : 'text-text-3 hover:text-text-2'
                  }`}
                >
                  {r.label}
                </button>
              );
            })}
          </div>

          <div className="inline-flex bg-surface-2 p-1 rounded-lg border border-border">
            <button
              onClick={() => setChartStyle('area')}
              className={`px-2 py-1 text-[10px] font-interface font-bold uppercase rounded transition-all cursor-pointer ${
                chartStyle === 'area'
                  ? 'bg-surface-3 text-accent border border-accent/20'
                  : 'text-text-3 hover:text-text-2'
              }`}
            >
              {localT('AIRES', 'AREA')}
            </button>
            <button
              onClick={() => setChartStyle('line')}
              className={`px-2 py-1 text-[10px] font-interface font-bold uppercase rounded transition-all cursor-pointer ${
                chartStyle === 'line'
                  ? 'bg-surface-3 text-accent border border-accent/20'
                  : 'text-text-3 hover:text-text-2'
              }`}
            >
              {localT('LIGNES', 'LINE')}
            </button>
          </div>

          <button
            onClick={handleRefreshClick}
            disabled={isRefreshing}
            className="flex items-center justify-center p-2 bg-surface-2 hover:bg-surface-3 border border-border text-text-2 hover:text-accent rounded-lg transition-all cursor-pointer"
            title={localT('Rafraîchir les données', 'Refresh data')}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-accent' : ''}`} />
          </button>
        </div>
      </div>

      <MetricsOverviewCards
        lastSnap={lastSnap}
        cpuTrend={cpuTrend}
        ramTrend={ramTrend}
        diskTrend={diskTrend}
        cpuSpark={cpuSpark}
        ramSpark={ramSpark}
        diskSpark={diskSpark}
        focusedMetric={focusedMetric}
        onToggleMetric={handleToggleMetric}
        getStatus={getStatus}
      />

      <div className="grid gap-6 grid-cols-1">
        {(focusedMetric === 'all' || focusedMetric === 'cpu') && (
          <div className="p-5 border border-border rounded-2xl bg-surface/30 flex flex-col gap-4 backdrop-blur-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-[3px] bg-cyan-500/20" />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-cyan-400" />
                <span className="font-interface font-black text-xs uppercase tracking-widest text-text-1">
                  {localT('HISTORIQUE CPU', 'CPU HISTORICAL ACTIVITY')}
                </span>
              </div>
              {focusedMetric === 'cpu' && (
                <button
                  onClick={() => setFocusedMetric('all')}
                  className="px-2 py-1 text-[9px] font-interface font-bold border border-border hover:border-accent hover:text-accent rounded transition-all cursor-pointer"
                >
                  {localT('RETOUR AUX AUTRES', 'BACK TO OVERVIEW')}
                </button>
              )}
            </div>

            <div className="h-60 w-full mt-2 font-mono text-[10px]">
              <ResponsiveContainer width="100%" height="100%">
                {chartStyle === 'area' ? (
                  <AreaChart data={mappedHistory} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
                    <defs>
                      <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={METRIC_THEMES.cpu.stroke} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={METRIC_THEMES.cpu.stroke} stopOpacity={0.0} />
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
                      dataKey="cpu"
                      name={localT('Charge CPU', 'CPU Utilization')}
                      stroke={METRIC_THEMES.cpu.stroke}
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorCpu)"
                      activeDot={{ r: 5, strokeWidth: 2, fill: 'var(--surface)', stroke: 'var(--accent)', style: { cursor: 'pointer', filter: 'drop-shadow(0 0 4px var(--accent))' } }}
                    />
                  </AreaChart>
                ) : (
                  <LineChart data={mappedHistory} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
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
                      dataKey="cpu"
                      name={localT('Charge CPU', 'CPU Utilization')}
                      stroke={METRIC_THEMES.cpu.stroke}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 5, strokeWidth: 2, fill: 'var(--surface)', stroke: 'var(--accent)', style: { cursor: 'pointer', filter: 'drop-shadow(0 0 4px var(--accent))' } }}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {(focusedMetric === 'all' || focusedMetric === 'ram') && (
          <div className="p-5 border border-border rounded-2xl bg-surface/30 flex flex-col gap-4 backdrop-blur-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-[3px] bg-purple-500/20" />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-purple-400" />
                <span className="font-interface font-black text-xs uppercase tracking-widest text-text-1">
                  {localT('HISTORIQUE MÉMOIRE RAM', 'MEMORY RAM HISTORICAL ACTIVITY')}
                </span>
              </div>
              {focusedMetric === 'ram' && (
                <button
                  onClick={() => setFocusedMetric('all')}
                  className="px-2 py-1 text-[9px] font-interface font-bold border border-border hover:border-accent hover:text-accent rounded transition-all cursor-pointer"
                >
                  {localT('RETOUR AUX AUTRES', 'BACK TO OVERVIEW')}
                </button>
              )}
            </div>

            <div className="h-60 w-full mt-2 font-mono text-[10px]">
              <ResponsiveContainer width="100%" height="100%">
                {chartStyle === 'area' ? (
                  <AreaChart data={mappedHistory} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
                    <defs>
                      <linearGradient id="colorRam" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={METRIC_THEMES.ram.stroke} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={METRIC_THEMES.ram.stroke} stopOpacity={0.0} />
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
                      dataKey="ram"
                      name={localT('Charge RAM', 'RAM Utilization')}
                      stroke={METRIC_THEMES.ram.stroke}
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorRam)"
                      activeDot={{ r: 5, strokeWidth: 2, fill: 'var(--surface)', stroke: 'var(--accent)', style: { cursor: 'pointer', filter: 'drop-shadow(0 0 4px var(--accent))' } }}
                    />
                  </AreaChart>
                ) : (
                  <LineChart data={mappedHistory} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
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
                      dataKey="ram"
                      name={localT('Charge RAM', 'RAM Utilization')}
                      stroke={METRIC_THEMES.ram.stroke}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 5, strokeWidth: 2, fill: 'var(--surface)', stroke: 'var(--accent)', style: { cursor: 'pointer', filter: 'drop-shadow(0 0 4px var(--accent))' } }}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {(focusedMetric === 'all' || focusedMetric === 'disk') && (
          <div className="p-5 border border-border rounded-2xl bg-surface/30 flex flex-col gap-4 backdrop-blur-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-[3px] bg-amber-500/20" />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-amber-400" />
                <span className="font-interface font-black text-xs uppercase tracking-widest text-text-1">
                  {localT('HISTORIQUE DE STOCKAGE DES DISQUES', 'DISK STORAGE HISTORY')}
                </span>
              </div>
              {focusedMetric === 'disk' && (
                <button
                  onClick={() => setFocusedMetric('all')}
                  className="px-2 py-1 text-[9px] font-interface font-bold border border-border hover:border-accent hover:text-accent rounded transition-all cursor-pointer"
                >
                  {localT('RETOUR AUX AUTRES', 'BACK TO OVERVIEW')}
                </button>
              )}
            </div>

            <div className="h-60 w-full mt-2 font-mono text-[10px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={diskChartData} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
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
                      style: { letterSpacing: '0.05em', fontWeight: 'bold' }
                    }}
                  />
                  {uniqueMounts.length === 0 ? (
                    <Line
                      type="monotone"
                      dataKey="Global"
                      name={localT('Disque Principal', 'Main Disk')}
                      stroke={METRIC_THEMES.disk.stroke}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 5, strokeWidth: 2, fill: 'var(--surface)', stroke: 'var(--accent)', style: { cursor: 'pointer', filter: 'drop-shadow(0 0 4px var(--accent))' } }}
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
                        activeDot={{ r: 5, strokeWidth: 2, fill: 'var(--surface)', stroke: 'var(--accent)', style: { cursor: 'pointer', filter: 'drop-shadow(0 0 4px var(--accent))' } }}
                      />
                    ))
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      {disks.length > 0 && (
        <div className="space-y-4">
          <h4 className="font-interface font-black text-xs uppercase tracking-widest text-text-3 px-1">
            {t('metrics.disks_title')}
          </h4>
          <DiskMountCards disks={disks} />
        </div>
      )}
    </div>
  );
};
