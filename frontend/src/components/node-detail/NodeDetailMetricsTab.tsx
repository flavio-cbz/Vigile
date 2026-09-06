import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, RotateCw } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { StatsPoint, NodeBaseline, AlertRecord } from './types';
import type { StatsSnapshot } from '../../hooks/useNodeDetailData';
import { estimateDiskSaturation } from './diskUtils';
import { formatRelativeDuration } from '../../utils/formatTime';
import { MetricsOverview, type TimeRangePreset } from './MetricsOverview';
import { MetricCharts } from './MetricCharts';
import { MetricCards } from './MetricCards';
import { DiskMountCards } from './DiskMountCards';
import { AlertDetailModal } from './AlertDetailModal';

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

const MIN_REFRESH_SPIN_MS = 800;

export const NodeDetailMetricsTab: React.FC<{
  statsHistory?: StatsPoint[];
  fullDiskHistory?: StatsSnapshot[];
  loading: boolean;
  statsError?: string | null;
  nodeId?: string;
  onRefresh: () => void;
  timeRange: TimeRangePreset;
  onSetTimeRange: (preset: TimeRangePreset, customStartSec?: number, customEndSec?: number) => void;
  dataWindowHours?: number;
  observationReady?: boolean;
  nodeBaseline?: NodeBaseline | null;
  nodeAlerts?: AlertRecord[];
}> = ({
  statsHistory = [], fullDiskHistory = [], loading, statsError, nodeId, onRefresh, timeRange, onSetTimeRange,
  dataWindowHours, observationReady = true, nodeBaseline, nodeAlerts,
}) => {
  const { locale, t } = useLocale();
  const [focusedMetric, setFocusedMetric] = useState<'all' | 'cpu' | 'ram' | 'disk'>('all');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<AlertRecord | null>(null);
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshStartRef = useRef(0);

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const [lastRefreshed, setLastRefreshed] = useState(() =>
    new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  );
  useEffect(() => {
    if (!loading && statsHistory) {
      setLastRefreshed(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    }
  }, [loading, statsHistory]);

  useEffect(() => {
    return () => {
      if (refreshTimeoutRef.current) clearTimeout(refreshTimeoutRef.current);
    };
  }, []);

  // Single owner of the isRefreshing lifecycle: the click arms it, this effect
  // retires it once the parent fetch settles AND the minimum spin duration elapsed.
  useEffect(() => {
    if (!isRefreshing) return;
    if (loading) return;
    const elapsed = Date.now() - refreshStartRef.current;
    const remaining = Math.max(0, MIN_REFRESH_SPIN_MS - elapsed);
    refreshTimeoutRef.current = setTimeout(() => setIsRefreshing(false), remaining);
    return () => {
      if (refreshTimeoutRef.current) clearTimeout(refreshTimeoutRef.current);
    };
  }, [isRefreshing, loading]);

  const handleRefreshClick = () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    refreshStartRef.current = Date.now();
    onRefresh();
  };

  const handleTimeRangeChange = (preset: TimeRangePreset, customStartSec?: number, customEndSec?: number) => {
    onSetTimeRange(preset, customStartSec, customEndSec);
  };

  const filteredHistory = useMemo(() => statsHistory || [], [statsHistory]);

  const mappedHistory = useMemo(() => {
    return filteredHistory.map((point, idx) => ({
      ...point,
      chartIndex: idx,
    }));
  }, [filteredHistory]);

  const lastSnap = filteredHistory[filteredHistory.length - 1] || null;

  const cpuHistory = useMemo(() => filteredHistory.map(p => p.cpu), [filteredHistory]);
  const ramHistory = useMemo(() => filteredHistory.map(p => p.ram), [filteredHistory]);
  const diskHistory = useMemo(() => filteredHistory.map(p => p.disk), [filteredHistory]);

  const uniqueMounts = useMemo(() => {
    const set = new Set<string>();
    filteredHistory.forEach(point => {
      if (point.disks) {
        point.disks.forEach(d => {
          if (d.mount_point !== '/boot/efi') {
            set.add(d.mount_point);
          }
        });
      }
    });
    return Array.from(set);
  }, [filteredHistory]);

  const DISK_COLORS = ['#f59e0b', '#10b981', '#3b82f6', '#ec4899', '#8b5cf6', '#06b6d4'];

  const diskChartData = useMemo(() => {
    return filteredHistory.map((point, idx) => {
      const dataPoint: Record<string, unknown> = {
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
    const lastSnap = filteredHistory[filteredHistory.length - 1];
    const disks = (lastSnap?.disks || []).filter(d => d.mount_point !== '/boot/efi');
    const diskHistoryForEstimate = fullDiskHistory.length > 0 ? fullDiskHistory : filteredHistory;
    const estimates = estimateDiskSaturation(diskHistoryForEstimate);
    return disks.map(d => ({
      ...d,
      days_left: estimates[d.mount_point]?.days_left ?? null,
      growth_gb_per_day: estimates[d.mount_point]?.growth_gb_per_day ?? null,
      confidence: estimates[d.mount_point]?.confidence ?? 'none',
      hours_collected: estimates[d.mount_point]?.hours_collected ?? 0,
      is_noisy: estimates[d.mount_point]?.is_noisy ?? false,
    }));
  }, [filteredHistory, fullDiskHistory]);

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
    const point = filteredHistory[idx];
    const lastPoint = filteredHistory[filteredHistory.length - 1];
    if (!point || !lastPoint) return '';

    const diffSec = point.collected_at != null && lastPoint.collected_at != null
      ? point.collected_at - lastPoint.collected_at
      : (idx - (filteredHistory.length - 1)) * 60;

    if (Math.abs(diffSec) < 1) return localT('Maintenant', 'Now');
    return formatRelativeDuration(diffSec);
  };

  const handleToggleMetric = (metric: 'cpu' | 'ram' | 'disk') => {
    setFocusedMetric(prev => prev === metric ? 'all' : metric);
  };

  if (loading && filteredHistory.length === 0) {
    return (
      <div className="py-24 text-center text-text-3 flex flex-col items-center justify-center gap-3">
        <Spinner size="md" />
        <span className="font-interface text-xs uppercase tracking-widest text-accent animate-pulse">
          {t('node_detail.metrics_loading')}
        </span>
      </div>
    );
  }

  if (filteredHistory.length === 0) {
    // Failed load with nothing to show: surface the error instead of a misleading "no data" state
    if (statsError && !loading) {
      return (
        <div className="py-24 border rounded-2xl bg-red-500/10 border-red-500/20 text-center flex flex-col items-center justify-center gap-3">
          <Activity className="w-8 h-8 text-severity-critical opacity-70" />
          <span className="font-interface text-xs font-semibold text-severity-critical">
            {t('node_detail.metrics_load_error')}
          </span>
          <button
            onClick={handleRefreshClick}
            disabled={isRefreshing}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t('node_detail.metrics_retry')}
          </button>
        </div>
      );
    }
    return (
      <div className="py-24 border border-dashed border-border rounded-2xl bg-surface/40 text-center text-text-3 flex flex-col items-center justify-center gap-2">
        <Activity className="w-8 h-8 text-text-3 opacity-40" />
        <span className="font-interface text-xs font-semibold">{t('node_detail.metrics_empty')}</span>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {statsError && (
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 rounded-lg border bg-red-500/10 border-red-500/20">
          <span className="font-interface text-xs font-semibold text-severity-critical">
            {t('node_detail.metrics_load_error')}
          </span>
          <button
            onClick={handleRefreshClick}
            disabled={isRefreshing}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer"
          >
            <RotateCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t('node_detail.metrics_retry')}
          </button>
        </div>
      )}

      <MetricsOverview
        timeRange={timeRange}
        isRefreshing={isRefreshing}
        lastRefreshed={lastRefreshed}
        locale={locale}
        nodeId={nodeId}
        onTimeRangeChange={handleTimeRangeChange}
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
        onSelectAlert={setSelectedAlert}
      />

    {enrichedDisks.length > 0 && (
      <div className="space-y-4">
        <h4 className="font-interface font-black text-xs uppercase tracking-widest text-text-3 px-1">
          {t('metrics.disks_title')}
        </h4>
        <DiskMountCards disks={enrichedDisks} observationReady={observationReady} />
      </div>
    )}

      <AlertDetailModal
        alert={selectedAlert}
        locale={locale}
        onClose={() => setSelectedAlert(null)}
      />
    </div>
  );
};
