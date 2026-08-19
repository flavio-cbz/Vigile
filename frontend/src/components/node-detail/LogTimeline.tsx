import React from 'react';
import type { LogHistogramRecord } from './types';
import { useLocale } from '../../i18n';

interface LogTimelineProps {
  histogram: LogHistogramRecord | null;
  loading: boolean;
  selectedHour: string | null;
  onSelectHour: (hour: string | null, since?: string, until?: string) => void;
}

export const LogTimeline: React.FC<LogTimelineProps> = ({
  histogram,
  loading,
  selectedHour,
  onSelectHour,
}) => {
  const { t } = useLocale();

  const buckets = histogram?.buckets && histogram.buckets.length > 0
    ? histogram.buckets
    : Array.from({ length: 24 }, (_, i) => ({
        hour: `${String(i).padStart(2, '0')}h`,
        timestamp: Date.now() / 1000 - (23 - i) * 3600,
        info: 0,
        warn: 0,
        error: 0,
        total: 0,
      }));

  const totalErrors = histogram?.total_errors ?? 0;
  const totalWarnings = histogram?.total_warnings ?? 0;
  const totalLines = histogram?.total_lines ?? 0;

  const maxBucketTotal = Math.max(...buckets.map((b) => b.total), 10);

  const handleBarClick = (hour: string, timestamp: number) => {
    if (selectedHour === hour) {
      onSelectHour(null);
    } else {
      const sinceDate = new Date(timestamp * 1000);
      const untilDate = new Date((timestamp + 3600) * 1000);
      const sinceStr = sinceDate.toISOString().replace('T', ' ').substring(0, 19);
      const untilStr = untilDate.toISOString().replace('T', ' ').substring(0, 19);
      onSelectHour(hour, sinceStr, untilStr);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-lg p-4 space-y-3 font-interface select-none">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-bold uppercase tracking-wider text-text-3">
            {t('node_detail.logs_timeline_title') || 'Activité 24h'}
          </span>
          {selectedHour && (
            <div className="inline-flex items-center gap-2 font-mono text-[11px] text-accent bg-accent/10 px-2 py-0.5 rounded border border-accent/30">
              <span>{t('node_detail.logs_filtered_hour') || 'Filtre heure'} : <strong>{selectedHour}</strong></span>
              <button
                onClick={() => onSelectHour(null)}
                className="text-text-2 hover:text-text-1 cursor-pointer font-bold ml-1 text-xs"
                title={t('common.reset') || 'Réinitialiser'}
              >
                ×
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 font-mono text-[11.5px] text-text-2">
          <span>{t('common.total') || 'Total'} : <strong className="text-text-1">{totalLines.toLocaleString()}</strong></span>
          <span>·</span>
          <span className={totalErrors > 0 ? 'text-red-400 font-semibold' : 'text-text-3'}>
            ● {totalErrors} {t('node_detail.logs_errors') || 'erreurs'}
          </span>
          <span>·</span>
          <span className={totalWarnings > 0 ? 'text-amber-400 font-semibold' : 'text-text-3'}>
            ● {totalWarnings} {t('node_detail.logs_warnings') || 'avertissements'}
          </span>
        </div>
      </div>

      <div className="flex items-end gap-1 h-14 border-b border-border/60 pb-1 relative">
        {loading && (
          <div className="absolute inset-0 bg-surface/40 backdrop-blur-xs flex items-center justify-center z-10">
            <span className="text-[11px] text-text-3 font-mono">...</span>
          </div>
        )}
        {buckets.map((b, idx) => {
          const isSelected = selectedHour === b.hour;
          const total = b.total || 0;
          const errHeight = (b.error / maxBucketTotal) * 48;
          const warnHeight = (b.warn / maxBucketTotal) * 48;
          const infoHeight = Math.max(((b.info || (total > 0 ? total : 0)) / maxBucketTotal) * 48, total > 0 ? 4 : 2);

          return (
            <div
              key={b.hour + idx}
              onClick={() => handleBarClick(b.hour, b.timestamp)}
              className={`group relative flex-1 h-full flex flex-col justify-end gap-0.5 cursor-pointer rounded-t transition-all ${
                isSelected ? 'ring-1.5 ring-accent bg-accent/10' : 'hover:bg-surface-2'
              }`}
            >
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-30 pointer-events-none bg-surface-3 border border-border text-text-1 px-2 py-1 rounded text-[10px] font-mono whitespace-nowrap shadow-xl">
                <div><strong>{b.hour}</strong> : {total} logs</div>
                <div className="text-red-400">{b.error} err · {b.warn} warn · {b.info} info</div>
              </div>

              {b.error > 0 && (
                <div
                  style={{ height: `${Math.max(errHeight, 4)}px` }}
                  className="w-full bg-red-500 rounded-xs"
                />
              )}
              {b.warn > 0 && (
                <div
                  style={{ height: `${Math.max(warnHeight, 3)}px` }}
                  className="w-full bg-amber-500 rounded-xs"
                />
              )}
              <div
                style={{ height: `${infoHeight}px` }}
                className={`w-full rounded-xs transition-colors ${
                  total > 0 ? 'bg-slate-700 group-hover:bg-slate-600' : 'bg-surface-2/60'
                }`}
              />
            </div>
          );
        })}
      </div>

      <div className="flex justify-between font-mono text-[9.5px] text-text-3 px-0.5">
        <span>00h</span>
        <span>04h</span>
        <span>08h</span>
        <span>12h</span>
        <span>16h</span>
        <span>20h</span>
        <span>24h</span>
      </div>
    </div>
  );
};
