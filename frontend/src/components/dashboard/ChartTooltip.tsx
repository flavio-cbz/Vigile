import React from 'react';
import type { BarData } from './TrendBar';

interface ChartTooltipProps {
  bar: BarData;
}

export const ChartTooltip: React.FC<ChartTooltipProps> = ({ bar }) => {
  return (
    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 pointer-events-none">
      <div className="bg-surface-2 border border-border-strong text-text-1 text-[10px] rounded p-2 shadow-xl whitespace-nowrap flex flex-col gap-0.5">
        <span className="font-mono text-text-3">{bar.label}</span>
        <span className="font-semibold">{bar.details}</span>
      </div>
      <div className="w-1.5 h-1.5 bg-surface-2 border-r border-b border-border-strong rotate-45 absolute -bottom-1 left-1/2 -translate-x-1/2 z-40" />
    </div>
  );
};
