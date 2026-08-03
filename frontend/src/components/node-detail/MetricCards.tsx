import React from 'react';
import { MetricsOverviewCards } from './MetricsOverviewCards';
import type { StatsPoint } from './types';

interface MetricCardsProps {
  lastSnap: StatsPoint | undefined;
  cpuTrend: { dir: string; val: number };
  ramTrend: { dir: string; val: number };
  diskTrend: { dir: string; val: number };
  cpuSpark: { line: string; area: string };
  ramSpark: { line: string; area: string };
  diskSpark: { line: string; area: string };
  focusedMetric: 'all' | 'cpu' | 'ram' | 'disk';
  onToggleMetric: (metric: 'cpu' | 'ram' | 'disk') => void;
  getStatus: (val: number, type: 'cpu' | 'ram' | 'disk') => { text: string; bg: string };
  dataWindowHours?: number;
}

export const MetricCards: React.FC<MetricCardsProps> = ({
  lastSnap, cpuTrend, ramTrend, diskTrend,
  cpuSpark, ramSpark, diskSpark,
  focusedMetric, onToggleMetric, getStatus,
  dataWindowHours,
}) => {
  return (
    <MetricsOverviewCards
      lastSnap={lastSnap}
      cpuTrend={cpuTrend}
      ramTrend={ramTrend}
      diskTrend={diskTrend}
      cpuSpark={cpuSpark}
      ramSpark={ramSpark}
      diskSpark={diskSpark}
      focusedMetric={focusedMetric}
      onToggleMetric={onToggleMetric}
      getStatus={getStatus}
      dataWindowHours={dataWindowHours}
    />
  );
};
