import React, { useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { StatsPoint, DiskMount, NodeBaseline, AlertRecord } from './types';
import { estimateDiskSaturation } from './diskUtils';
import { MetricsOverview, type TimeRangePreset } from './MetricsOverview';
import { MetricCharts } from './MetricCharts';
import { MetricCards } from './MetricCards';
import { DiskMountCards } from './DiskMountCards';

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
  nodeId?: string;
  onRefresh: () => void;
  onFetchHistoryWithRange?: (startSec?: number, endSec?: number) => void;
  dataWindowHours?: number;
  observationReady?: boolean;
  nodeBaseline?: NodeBaseline | null;
  nodeAlerts?: AlertRecord[];
}> = ({
  statsHistory, loading, nodeId, onRefresh, onFetchHistoryWithRange,
  dataWindowHours, observationReady = true, nodeBaseline, nodeAlerts,
}) => {
  const { locale, t } = useLocale();
  const [timeRange, setTimeRange] = useState<TimeRangePreset>('1h');
  const [chartStyle, setChartStyle] = useState<'area' | 'line'>('area');
  const [focusedMetric, setFocusedMetric] = useState<'all' | 'cpu' | 'ram' | 'disk'>('all');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const lastRefreshed = useMemo(
    () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    [],
  );

  const handleRefreshClick = () => {
    setIsRefreshing(true);
    onRefresh();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  const handleTimeRangeChange = (preset: TimeRangePreset, customStartSec?: number, customEndSec?: number) => {
    setTimeRange(preset);
    if (!onFetchHistoryWithRange) return;

    if (preset === 'custom' && customStartSec && customEndSec) {
      onFetchHistoryWithRange(customStartSec, customEndSec);
      return;
    }

    const now = Math.floor(Date.now() / 1000);
    const durationMap: Record<string, number> = {
      '1h': 3600,
      '6h': 21600,
      '12h': 43200,
      '24h': 86400,
      '7d': 604800,
      '30d': 2592000,
    };

    const duration = durationMap[preset] || 3600;
    onFetchHistoryWithRange(now - duration, now);
  };

  const filteredHistory = statsHistory;

  const mappedHistory = useMemo(() => {
    return filteredHistory.map((point, idx) => ({
      ...point,
      chartIndex: idx,
    }));
  }, [filteredHistory]);

  const lastSnap = statsHistory[statsHistory.length - 1];


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

  const enrichedDisks = useMemo(() => {
    const lastSnap = statsHistory[statsHistory.length - 1];
    const disks = lastSnap?.disks || [];
    const estimates = estimateDiskSaturation(statsHistory);
    return disks.map(d => ({
      ...d,
      days_left: estimates[d.mount_point]?.days_left ?? null,
      growth_gb_per_day: estimates[d.mount_point]?.growth_gb_per_day ?? null,
    }));
  }, [statsHistory]);



  const getStatus = (val: number, type: 'cpu' | 'ram' | 'disk') => {
    const mBase = nodeBaseline?.metrics?.[type];
    if (mBase && !nodeBaseline?.is_limited) {
      if (val >= mBase.absolute_critical || val >= mBase.p99) {
        return { text: localT('Critique absolu', 'Absolute critical'), bg: 'bg-red-500/10 text-severity-critical border-red-500/20' };
      }
      if (val >= mBase.p90) {
        return { text: localT('Critique relatif', 'Relative critical'), bg: 'bg-amber-500/10 text-severity-warning border-amber-500/20' };
      }
      if (val >= mBase.p75) {
        return { text: localT('Élevé', 'Elevated'), bg: 'bg-amber-500/10 text-zone-elevated border-amber-500/20' };
      }
      return { text: localT('Normal', 'Normal'), bg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' };
    }

    const limits = type === 'disk' ? { warn: 70, crit: 85 } : { warn: 50, crit: 80 };
    if (val >= limits.crit) return { text: localT('Critique absolu', 'Absolute critical'), bg: 'bg-red-500/10 text-severity-critical border-red-500/20' };
    if (val >= limits.warn) return { text: localT('Élevé', 'Elevated'), bg: 'bg-amber-500/10 text-zone-elevated border-amber-500/20' };
    return { text: localT('Normal', 'Normal'), bg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' };
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

  return (
    <div className="space-y-8 animate-fade-in">
      <MetricsOverview
        timeRange={timeRange}
        chartStyle={chartStyle}
        isRefreshing={isRefreshing}
        lastRefreshed={lastRefreshed}
        locale={locale}
        nodeId={nodeId}
        onTimeRangeChange={handleTimeRangeChange}
        onChartStyleChange={setChartStyle}
        onRefresh={handleRefreshClick}
      />

      <MetricCards
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
        dataWindowHours={dataWindowHours}
      />

      <MetricCharts
        mappedHistory={mappedHistory}
        chartStyle={chartStyle}
        locale={locale}
        focusedMetric={focusedMetric}
        onSetFocusedMetric={setFocusedMetric}
        getRelativeTimeLabel={getRelativeTimeLabel}
        filteredHistory={filteredHistory}
        diskChartData={diskChartData}
        uniqueMounts={uniqueMounts}
        DISK_COLORS={DISK_COLORS}
        baseline={nodeBaseline}
        alerts={nodeAlerts}
      />

    {enrichedDisks.length > 0 && (
      <div className="space-y-4">
        <h4 className="font-interface font-black text-xs uppercase tracking-widest text-text-3 px-1">
          {t('metrics.disks_title')}
        </h4>
        <DiskMountCards disks={enrichedDisks} observationReady={observationReady} />
      </div>
    )}
    </div>
  );
};
