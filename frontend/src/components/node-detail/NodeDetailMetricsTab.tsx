import React, { useMemo, useState, useEffect } from 'react';
import {
  Cpu,
  Database,
  Layers,
  HardDrive,
  TrendingUp,
  TrendingDown,
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

// HSL Colors matching dashboard design tokens
const METRIC_THEMES = {
  cpu: {
    stroke: '#06B6D4', // Cyan
    fillGradStart: 'rgba(6, 182, 212, 0.25)',
    fillGradEnd: 'rgba(6, 182, 212, 0.0)',
    glow: 'rgba(6, 182, 212, 0.15)',
  },
  ram: {
    stroke: '#8B5CF6', // Purple/Violet
    fillGradStart: 'rgba(139, 92, 246, 0.25)',
    fillGradEnd: 'rgba(139, 92, 246, 0.0)',
    glow: 'rgba(139, 92, 246, 0.15)',
  },
  disk: {
    stroke: '#F59E0B', // Amber
    fillGradStart: 'rgba(245, 158, 11, 0.25)',
    fillGradEnd: 'rgba(245, 158, 11, 0.0)',
    glow: 'rgba(245, 158, 11, 0.15)',
  },
};

// Helper to format bytes to human readable format
const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'Ko', 'Mo', 'Go', 'To'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

// SVG Sparkline path generator
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

// Sparkline React component (Stable Reference)
const Sparkline: React.FC<{ paths: { line: string; area: string }; color: string }> = ({ paths, color }) => {
  if (!paths.line) return null;
  return (
    <svg width="120" height="32" className="overflow-visible opacity-80">
      <defs>
        <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={paths.area} fill={`url(#spark-${color})`} />
      <path d={paths.line} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

// Custom tooltips for graphs (Stable Reference)
const CustomChartTooltip: React.FC<any> = ({ active, payload, label, locale, history }) => {
  if (!active || !payload || payload.length === 0) return null;

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  // Retrieve actual time from history using index
  const index = typeof label === 'number' ? label : parseInt(label, 10);
  const point = history && history[index] ? history[index] : null;
  const timeLabel = point ? point.time : label;

  const relativeDiff = history ? index - (history.length - 1) : 0;
  const relativeLabel = relativeDiff === 0 
    ? localT('Maintenant', 'Now') 
    : `${relativeDiff}m`;

  return (
    <div className="bg-surface/95 backdrop-blur-md border border-border-strong rounded-xl p-3 shadow-2xl animate-fade-in flex flex-col gap-1.5 min-w-[160px] max-w-[240px] z-50">
      <div className="text-[9px] font-mono text-text-3 uppercase tracking-wider border-b border-border/40 pb-1 mb-1">
        {localT('Temps', 'Time')} : {relativeLabel} {timeLabel ? `(${timeLabel})` : ''}
      </div>
      
      <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
        {payload.map((item: any, idx: number) => {
          const color = item.stroke || item.color;
          const name = item.name;
          const value = item.value;
          return (
            <div key={idx} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
              <span className="font-interface text-[10px] font-bold uppercase text-text-2 truncate max-w-[120px]">{name}</span>
              <span className="ml-auto font-mono text-[11px] font-bold text-text-1">
                {typeof value === 'number' ? `${value.toFixed(1)}%` : value}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

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
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  // Local multi-language dictionary for completely customized UI
  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  useEffect(() => {
    setLastRefreshed(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
  }, [statsHistory]);

  const handleRefreshClick = () => {
    setIsRefreshing(true);
    onRefresh();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  // Determine availability of time ranges dynamically
  const is30mAvailable = statsHistory.length >= 30;
  const is12hAvailable = statsHistory.length >= 720;
  const is24hAvailable = statsHistory.length >= 1440;

  // Filter history based on time selector (or show all if selected range is not available/longer than history)
  const filteredHistory = useMemo(() => {
    if (timeRange === '30m' && statsHistory.length >= 30) return statsHistory.slice(-30);
    if (timeRange === '12h' && statsHistory.length >= 720) return statsHistory.slice(-720);
    if (timeRange === '24h' && statsHistory.length >= 1440) return statsHistory.slice(-1440);
    return statsHistory; // fallback to show everything
  }, [statsHistory, timeRange]);

  // Map filtered history to include a unique index coordinate to prevent coordinate overlap on tooltip
  const mappedHistory = useMemo(() => {
    return filteredHistory.map((point, idx) => ({
      ...point,
      chartIndex: idx,
    }));
  }, [filteredHistory]);

  const lastSnap = statsHistory[statsHistory.length - 1];
  const disks = lastSnap?.disks || [];

  // Extract metric histories for ribbon overview
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
      const dataPoint: any = {
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

  // Compute trend metrics
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

  // Generate sparklines
  const cpuSpark = useMemo(() => generateSparklinePaths(cpuHistory.slice(-15)), [cpuHistory]);
  const ramSpark = useMemo(() => generateSparklinePaths(ramHistory.slice(-15)), [ramHistory]);
  const diskSpark = useMemo(() => generateSparklinePaths(diskHistory.slice(-15)), [diskHistory]);

  // Get status label color helper
  const getStatus = (val: number, type: 'cpu' | 'ram' | 'disk') => {
    const limits = type === 'disk' ? { warn: 70, crit: 85 } : { warn: 50, crit: 80 };
    if (val >= limits.crit) return { text: localT('Critique', 'Critical'), bg: 'bg-red-500/10 text-severity-critical border-red-500/20' };
    if (val >= limits.warn) return { text: localT('Avertissement', 'Warning'), bg: 'bg-amber-500/10 text-severity-warning border-amber-500/20' };
    return { text: localT('Nominal', 'Nominal'), bg: 'bg-emerald-500/10 text-severity-ok border-emerald-500/20' };
  };

  // Relative time helper mapping index offset to user-friendly "-X min" or "Now"
  const getRelativeTimeLabel = (idx: number) => {
    const diff = idx - (filteredHistory.length - 1);
    if (diff === 0) return localT('Maintenant', 'Now');
    return `${diff}m`;
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
      
      {/* Interactive Control Header */}
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
          {/* Time range picker */}
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

          {/* Chart Style Toggle */}
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

          {/* Refresh Action */}
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

      {/* Metrics Ribbon (Overview Cards) */}
      <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
        
        {/* CPU overview card */}
        <div
          onClick={() => setFocusedMetric(focusedMetric === 'cpu' ? 'all' : 'cpu')}
          className={`p-4 rounded-xl bg-surface/50 border backdrop-blur-md cursor-pointer transition-all duration-300 flex flex-col justify-between h-36 ${
            focusedMetric === 'cpu'
              ? 'border-cyan-500/80 shadow-[0_0_20px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/20'
              : 'border-border hover:border-cyan-500/40 hover:shadow-[0_0_15px_rgba(6,182,212,0.06)]'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 shadow-inner">
                <Cpu className="w-4 h-4" />
              </div>
              <span className="font-interface font-extrabold uppercase text-[10px] tracking-wider text-text-2">
                CPU
              </span>
            </div>
            <span className={`text-[9px] font-mono px-2 py-0.5 rounded-full border ${getStatus(lastSnap?.cpu ?? 0, 'cpu').bg}`}>
              {getStatus(lastSnap?.cpu ?? 0, 'cpu').text}
            </span>
          </div>

          <div className="flex items-end justify-between mt-2">
            <div>
              <div className="font-mono text-3xl font-black text-text-1 tracking-tight">
                {(lastSnap?.cpu ?? 0).toFixed(1)}%
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                {cpuTrend.dir === 'up' ? (
                  <TrendingUp className="w-3.5 h-3.5 text-red-400" />
                ) : cpuTrend.dir === 'down' ? (
                  <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Activity className="w-3.5 h-3.5 text-text-3" />
                )}
                <span className={`font-mono text-[9px] font-bold ${
                  cpuTrend.dir === 'up' ? 'text-red-400' : cpuTrend.dir === 'down' ? 'text-emerald-400' : 'text-text-3'
                }`}>
                  {cpuTrend.dir !== 'flat' ? `${cpuTrend.val.toFixed(1)}%` : 'stable'}
                </span>
              </div>
            </div>

            <Sparkline paths={cpuSpark} color={METRIC_THEMES.cpu.stroke} />
          </div>
        </div>

        {/* RAM overview card */}
        <div
          onClick={() => setFocusedMetric(focusedMetric === 'ram' ? 'all' : 'ram')}
          className={`p-4 rounded-xl bg-surface/50 border backdrop-blur-md cursor-pointer transition-all duration-300 flex flex-col justify-between h-36 ${
            focusedMetric === 'ram'
              ? 'border-purple-500/80 shadow-[0_0_20px_rgba(139,92,246,0.15)] ring-1 ring-purple-500/20'
              : 'border-border hover:border-purple-500/40 hover:shadow-[0_0_15px_rgba(139,92,246,0.06)]'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 shadow-inner">
                <Database className="w-4 h-4" />
              </div>
              <span className="font-interface font-extrabold uppercase text-[10px] tracking-wider text-text-2">
                RAM
              </span>
            </div>
            <span className={`text-[9px] font-mono px-2 py-0.5 rounded-full border ${getStatus(lastSnap?.ram ?? 0, 'ram').bg}`}>
              {getStatus(lastSnap?.ram ?? 0, 'ram').text}
            </span>
          </div>

          <div className="flex items-end justify-between mt-2">
            <div>
              <div className="font-mono text-3xl font-black text-text-1 tracking-tight">
                {(lastSnap?.ram ?? 0).toFixed(1)}%
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                {ramTrend.dir === 'up' ? (
                  <TrendingUp className="w-3.5 h-3.5 text-red-400" />
                ) : ramTrend.dir === 'down' ? (
                  <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Activity className="w-3.5 h-3.5 text-text-3" />
                )}
                <span className={`font-mono text-[9px] font-bold ${
                  ramTrend.dir === 'up' ? 'text-red-400' : ramTrend.dir === 'down' ? 'text-emerald-400' : 'text-text-3'
                }`}>
                  {ramTrend.dir !== 'flat' ? `${ramTrend.val.toFixed(1)}%` : 'stable'}
                </span>
              </div>
            </div>

            <Sparkline paths={ramSpark} color={METRIC_THEMES.ram.stroke} />
          </div>
        </div>

        {/* Global Storage Overview */}
        <div
          onClick={() => setFocusedMetric(focusedMetric === 'disk' ? 'all' : 'disk')}
          className={`p-4 rounded-xl bg-surface/50 border backdrop-blur-md cursor-pointer transition-all duration-300 flex flex-col justify-between h-36 ${
            focusedMetric === 'disk'
              ? 'border-amber-500/80 shadow-[0_0_20px_rgba(245,158,11,0.15)] ring-1 ring-amber-500/20'
              : 'border-border hover:border-amber-500/40 hover:shadow-[0_0_15px_rgba(245,158,11,0.06)]'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 shadow-inner">
                <Layers className="w-4 h-4" />
              </div>
              <span className="font-interface font-extrabold uppercase text-[10px] tracking-wider text-text-2">
                STORAGE
              </span>
            </div>
            <span className={`text-[9px] font-mono px-2 py-0.5 rounded-full border ${getStatus(lastSnap?.disk ?? 0, 'disk').bg}`}>
              {getStatus(lastSnap?.disk ?? 0, 'disk').text}
            </span>
          </div>

          <div className="flex items-end justify-between mt-2">
            <div>
              <div className="font-mono text-3xl font-black text-text-1 tracking-tight">
                {(lastSnap?.disk ?? 0).toFixed(1)}%
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                {diskTrend.dir === 'up' ? (
                  <TrendingUp className="w-3.5 h-3.5 text-red-400" />
                ) : diskTrend.dir === 'down' ? (
                  <TrendingDown className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Activity className="w-3.5 h-3.5 text-text-3" />
                )}
                <span className={`font-mono text-[9px] font-bold ${
                  diskTrend.dir === 'up' ? 'text-red-400' : diskTrend.dir === 'down' ? 'text-emerald-400' : 'text-text-3'
                }`}>
                  {diskTrend.dir !== 'flat' ? `${diskTrend.val.toFixed(1)}%` : 'stable'}
                </span>
              </div>
            </div>

            <Sparkline paths={diskSpark} color={METRIC_THEMES.disk.stroke} />
          </div>
        </div>

      </div>

      {/* Main Detailed Chart Section */}
      <div className="grid gap-6 grid-cols-1">
        
        {/* Render CPU Chart if focused or if viewing 'all' */}
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
                    <Tooltip content={<CustomChartTooltip locale={locale} history={filteredHistory} />} />
                    <Area
                      type="monotone"
                      dataKey="cpu"
                      name={localT('Charge CPU', 'CPU Utilization')}
                      stroke={METRIC_THEMES.cpu.stroke}
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorCpu)"
                      activeDot={{ r: 4, strokeWidth: 1.5, fill: 'var(--surface)' }}
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
                    <Tooltip content={<CustomChartTooltip locale={locale} history={filteredHistory} />} />
                    <Line
                      type="monotone"
                      dataKey="cpu"
                      name={localT('Charge CPU', 'CPU Utilization')}
                      stroke={METRIC_THEMES.cpu.stroke}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, strokeWidth: 1.5, fill: 'var(--surface)' }}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Render RAM Chart if focused or if viewing 'all' */}
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
                    <Tooltip content={<CustomChartTooltip locale={locale} history={filteredHistory} />} />
                    <Area
                      type="monotone"
                      dataKey="ram"
                      name={localT('Charge RAM', 'RAM Utilization')}
                      stroke={METRIC_THEMES.ram.stroke}
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorRam)"
                      activeDot={{ r: 4, strokeWidth: 1.5, fill: 'var(--surface)' }}
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
                    <Tooltip content={<CustomChartTooltip locale={locale} history={filteredHistory} />} />
                    <Line
                      type="monotone"
                      dataKey="ram"
                      name={localT('Charge RAM', 'RAM Utilization')}
                      stroke={METRIC_THEMES.ram.stroke}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, strokeWidth: 1.5, fill: 'var(--surface)' }}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        )}
        {/* Render STORAGE multi-disk history chart */}
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
                  <Tooltip content={<CustomChartTooltip locale={locale} history={filteredHistory} />} />
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
                      activeDot={{ r: 4, strokeWidth: 1.5, fill: 'var(--surface)' }}
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
                        activeDot={{ r: 4, strokeWidth: 1.5, fill: 'var(--surface)' }}
                      />
                    ))
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

      </div>

      {/* Grid of Disk Mounts as premium visual cards */}
      {disks.length > 0 && (
        <div className="space-y-4">
          <h4 className="font-interface font-black text-xs uppercase tracking-widest text-text-3 px-1">
            {t('metrics.disks_title')}
          </h4>

          <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
            {disks.map((d: DiskMount, idx: number) => {
              const warningState = d.percent > 85 ? 'crit' : d.percent > 70 ? 'warn' : 'ok';
              
              const progressColors = {
                crit: { bar: 'bg-severity-critical', text: 'text-severity-critical', border: 'border-red-500/10' },
                warn: { bar: 'bg-severity-warning', text: 'text-severity-warning', border: 'border-amber-500/10' },
                ok: { bar: 'bg-accent', text: 'text-accent', border: 'border-amber-500/5' },
              }[warningState];

              return (
                <div key={idx} className={`bg-surface/50 border border-border rounded-2xl p-4 flex flex-col justify-between gap-4 backdrop-blur-sm transition-all duration-300 hover:border-accent/35 shadow-sm`}>
                  
                  {/* Card Header info */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-0.5 truncate">
                      <div className="font-interface font-black text-xs text-text-1 truncate" title={d.mount_point}>
                        {d.mount_point}
                      </div>
                      <div className="font-mono text-[9px] text-text-3">
                        {d.device} ({d.fs_type})
                      </div>
                    </div>
                    <div className="p-2 rounded-lg bg-surface border border-border shadow-inner text-text-3 shrink-0">
                      <HardDrive className="w-3.5 h-3.5" />
                    </div>
                  </div>

                  {/* Visual progress track */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between items-baseline font-mono text-[10px]">
                      <span className="text-text-3 font-semibold">
                        {formatBytes(d.used_bytes)} / {formatBytes(d.total_bytes)}
                      </span>
                      <span className={`font-bold ${progressColors.text}`}>
                        {d.percent.toFixed(0)}%
                      </span>
                    </div>

                    <div className="w-full bg-surface-2 rounded-full h-2 overflow-hidden border border-border shadow-inner">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${progressColors.bar}`}
                        style={{ width: `${d.percent}%` }}
                      />
                    </div>
                  </div>

                </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
};
