import React from 'react';
import { ChartTooltip } from './ChartTooltip';

export interface BarData {
  index: number;
  startTime: number;
  endTime: number;
  status: 'ok' | 'warning' | 'critical' | 'nodata';
  details: string;
  label: string;
  snapshots: Snapshot[];
}

export interface Snapshot {
  collected_at: number;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
}

interface TrendBarProps {
  bar: BarData;
  barIdx: number;
  isHovered: boolean;
  onHover: () => void;
  onLeave: () => void;
}

export const TrendBar: React.FC<TrendBarProps> = ({ bar, barIdx, isHovered, onHover, onLeave }) => {
  let colorClass = 'bg-text-3/20'; // nodata
  if (bar.status === 'ok') colorClass = 'bg-severity-ok/70 hover:bg-severity-ok';
  if (bar.status === 'warning') colorClass = 'bg-severity-warning/70 hover:bg-severity-warning';
  if (bar.status === 'critical') colorClass = 'bg-severity-critical/70 hover:bg-severity-critical';

  return (
    <div
      key={barIdx}
      className={`flex-1 h-6 rounded-sm transition-transform duration-100 hover:scale-y-125 cursor-pointer relative ${colorClass}`}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
    >
      {isHovered && <ChartTooltip bar={bar} />}
    </div>
  );
};
