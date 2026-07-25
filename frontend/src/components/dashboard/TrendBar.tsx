import React from 'react';

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
      {isHovered && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 pointer-events-none">
          <div className="bg-surface-2 border border-border-strong text-text-1 text-[10px] rounded p-2 shadow-xl whitespace-nowrap flex flex-col gap-0.5">
            <span className="font-mono text-text-3">{bar.label}</span>
            <span className="font-semibold">{bar.details}</span>
          </div>
          <div className="w-1.5 h-1.5 bg-surface-2 border-r border-b border-border-strong rotate-45 absolute -bottom-1 left-1/2 -translate-x-1/2 z-40" />
        </div>
      )}
    </div>
  );
};
