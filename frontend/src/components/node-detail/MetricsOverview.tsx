import React from 'react';
import { RefreshCw } from 'lucide-react';

interface MetricsOverviewProps {
  timeRange: '30m' | '12h' | '24h';
  chartStyle: 'area' | 'line';
  isRefreshing: boolean;
  lastRefreshed: string;
  locale: string;
  onTimeRangeChange: (range: '30m' | '12h' | '24h') => void;
  onChartStyleChange: (style: 'area' | 'line') => void;
  onRefresh: () => void;
  is30mAvailable: boolean;
  is12hAvailable: boolean;
  is24hAvailable: boolean;
}

export const MetricsOverview: React.FC<MetricsOverviewProps> = ({
  timeRange, chartStyle, isRefreshing, lastRefreshed, locale,
  onTimeRangeChange, onChartStyleChange, onRefresh,
  is30mAvailable, is12hAvailable, is24hAvailable,
}) => {
  const localT = (frText: string, enText: string) => {
    return locale === 'fr' ? frText : enText;
  };

  const timeRanges = [
    { id: '30m', label: localT('30 min', '30 min'), available: is30mAvailable },
    { id: '12h', label: localT('12h', '12h'), available: is12hAvailable },
    { id: '24h', label: localT('24h', '24h'), available: is24hAvailable },
  ] as const;

  return (
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
                onClick={() => onTimeRangeChange(r.id)}
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

        <div className="inline-flex bg-surface-2 p-1 rounded-lg border border-border">
          <button
            onClick={() => onChartStyleChange('area')}
            className={`px-2 py-1 text-[10px] font-interface font-bold uppercase rounded transition-all cursor-pointer ${
              chartStyle === 'area'
                ? 'bg-surface-3 text-accent border border-accent/20'
                : 'text-text-3 hover:text-text-2'
            }`}
          >
            {localT('AIRES', 'AREA')}
          </button>
          <button
            onClick={() => onChartStyleChange('line')}
            className={`px-2 py-1 text-[10px] font-interface font-bold uppercase rounded transition-all cursor-pointer ${
              chartStyle === 'line'
                ? 'bg-surface-3 text-accent border border-accent/20'
                : 'text-text-3 hover:text-text-2'
            }`}
          >
            {localT('LIGNES', 'LINE')}
          </button>
        </div>

        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="flex items-center justify-center p-2 bg-surface-2 hover:bg-surface-3 border border-border text-text-2 hover:text-accent rounded-lg transition-all cursor-pointer"
          title={localT('Rafraîchir les données', 'Refresh data')}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-accent' : ''}`} />
        </button>
      </div>
    </div>
  );
};
