import React, { useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { StatsPoint, DiskMount } from './types';
import { estimateDiskSaturation } from './diskUtils';
import { MetricsOverview } from './MetricsOverview';
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
    [],
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

  const enrichedDisks = useMemo(() => {
    const estimates = estimateDiskSaturation(statsHistory.map(s => s.disks || []));
    return disks.map(d => ({
      ...d,
      days_left: estimates[d.mount_point]?.days_left ?? null,
      growth_gb_per_day: estimates[d.mount_point]?.growth_gb_per_day ?? null,
    }));
  }, [disks, statsHistory]);


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

  return (
    <div className="space-y-8 animate-fade-in">
      <MetricsOverview
        timeRange={timeRange}
        chartStyle={chartStyle}
        isRefreshing={isRefreshing}
        lastRefreshed={lastRefreshed}
        locale={locale}
        onTimeRangeChange={setTimeRange}
        onChartStyleChange={setChartStyle}
        onRefresh={handleRefreshClick}
        is30mAvailable={is30mAvailable}
        is12hAvailable={is12hAvailable}
        is24hAvailable={is24hAvailable}
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
        disks={disks}
        t={t}
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
      />

    {enrichedDisks.length > 0 && (
      <div className="space-y-4">
        <h4 className="font-interface font-black text-xs uppercase tracking-widest text-text-3 px-1">
          {t('metrics.disks_title')}
        </h4>
        <DiskMountCards disks={enrichedDisks} />
      </div>
    )}
    </div>
  );
};
