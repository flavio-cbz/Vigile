import React from 'react';
import { Card, CardHeader, CardContent } from '../ui/Card';
import type { StatsPoint } from './types';

interface TooltipPayloadItem {
  name: string;
  value: number;
  color?: string;
  stroke?: string;
  fill?: string;
  dataKey?: string;
}

interface MetricsTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string | number;
  locale: string;
  history: StatsPoint[];
}

export const MetricsTooltip: React.FC<MetricsTooltipProps> = ({ active, payload, label, locale, history }) => {
  if (!active || !payload || payload.length === 0) return null;

  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const index = typeof label === 'number' ? label : parseInt(String(label), 10);
  const point = history && history[index] ? history[index] : null;
  const timeLabel = point ? point.time : label;

  const relativeDiff = history ? index - (history.length - 1) : 0;
  const relativeLabel = relativeDiff === 0 
    ? localT('Maintenant', 'Now') 
    : `${relativeDiff}m`;

  return (
    <Card className="backdrop-blur-md animate-fade-in min-w-[160px] max-w-[240px] z-50">
      <CardHeader>
        <div className="text-[9px] font-mono text-text-3 uppercase tracking-wider">
          {localT('Temps', 'Time')} : {relativeLabel} {timeLabel ? `(${timeLabel})` : ''}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
          {payload.map((item, idx) => {
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
      </CardContent>
    </Card>
  );
};
