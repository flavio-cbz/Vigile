import React from 'react';
import { MetricChart } from './MetricChart';
import type { StatsPoint, DiskMount, NodeBaseline, AlertRecord } from './types';

interface MetricChartsProps {
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

export const MetricCharts: React.FC<MetricChartsProps> = ({
  mappedHistory, locale, focusedMetric,
  onSetFocusedMetric, getRelativeTimeLabel, filteredHistory,
  diskChartData, uniqueMounts, DISK_COLORS, baseline, alerts,
  onSelectAlert,
}) => {
  return (
    <div className="grid gap-6 grid-cols-1">
      {(focusedMetric === 'all' || focusedMetric === 'cpu') && (
        <MetricChart
          metric="cpu"
          mappedHistory={mappedHistory}
          locale={locale}
          focusedMetric={focusedMetric}
          onSetFocusedMetric={onSetFocusedMetric}
          getRelativeTimeLabel={getRelativeTimeLabel}
          filteredHistory={filteredHistory}
          diskChartData={diskChartData}
          uniqueMounts={uniqueMounts}
          DISK_COLORS={DISK_COLORS}
          baseline={baseline}
          alerts={alerts}
          onSelectAlert={onSelectAlert}
        />
      )}

      {(focusedMetric === 'all' || focusedMetric === 'ram') && (
        <MetricChart
          metric="ram"
          mappedHistory={mappedHistory}
          locale={locale}
          focusedMetric={focusedMetric}
          onSetFocusedMetric={onSetFocusedMetric}
          getRelativeTimeLabel={getRelativeTimeLabel}
          filteredHistory={filteredHistory}
          diskChartData={diskChartData}
          uniqueMounts={uniqueMounts}
          DISK_COLORS={DISK_COLORS}
          baseline={baseline}
          alerts={alerts}
          onSelectAlert={onSelectAlert}
        />
      )}

      {(focusedMetric === 'all' || focusedMetric === 'disk') && (
        <MetricChart
          metric="disk"
          mappedHistory={mappedHistory}
          locale={locale}
          focusedMetric={focusedMetric}
          onSetFocusedMetric={onSetFocusedMetric}
          getRelativeTimeLabel={getRelativeTimeLabel}
          filteredHistory={filteredHistory}
          diskChartData={diskChartData}
          uniqueMounts={uniqueMounts}
          DISK_COLORS={DISK_COLORS}
          baseline={baseline}
          alerts={alerts}
          onSelectAlert={onSelectAlert}
        />
      )}
    </div>
  );
};

