import React from 'react';
import { HardDrive, TrendingUp, TrendingDown } from 'lucide-react';
import { useLocale } from '../../i18n';
import type { DiskMount } from './types';
import { getDiskSeverity } from './diskUtils';

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'Ko', 'Mo', 'Go', 'To'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

interface DiskMountCardsProps {
  disks: DiskMount[];
}

const SEVERITY_COLORS = {
  crit: {
    bar: 'bg-severity-critical',
    text: 'text-severity-critical',
    border: 'border-red-500/20',
    icon: 'text-severity-critical',
  },
  warn: {
    bar: 'bg-severity-warning',
    text: 'text-severity-warning',
    border: 'border-amber-500/20',
    icon: 'text-severity-warning',
  },
  ok: {
    bar: 'bg-emerald-500',
    text: 'text-emerald-400',
    border: 'border-emerald-500/10',
    icon: 'text-emerald-400',
  },
} as const;

function formatDaysLeft(
  days: number | null,
  t: (key: string, vars?: Record<string, unknown>) => string,
): string | null {
  if (days === null) return null;
  if (days < 1) return t('metrics.disk.saturation.today');
  if (days === 1) return t('metrics.disk.saturation.day');
  if (days < 30) return t('metrics.disk.saturation.days', { n: days });
  if (days < 365) return t('metrics.disk.saturation.months', { n: Math.round(days / 30) });
  return t('metrics.disk.saturation.years', { n: Math.round(days / 365) });
}

export const DiskMountCards: React.FC<DiskMountCardsProps> = ({ disks }) => {
  const { t } = useLocale();
  if (disks.length === 0) return null;

  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
      {disks.map((d, idx) => {
        const severity = getDiskSeverity(d.percent, d.days_left);
        const colors = SEVERITY_COLORS[severity];
        const daysLabel = formatDaysLeft(d.days_left, t);
        const growthPositive = d.growth_gb_per_day !== null && d.growth_gb_per_day !== undefined && d.growth_gb_per_day > 0;

        return (
          <div
            key={idx}
            className={`bg-surface/50 border ${colors.border} rounded-2xl p-4 flex flex-col justify-between gap-4 backdrop-blur-sm transition-all duration-300 hover:border-accent/35 shadow-sm`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-0.5 truncate">
                <div className="font-interface font-black text-xs text-text-1 truncate" title={d.mount_point}>
                  {d.mount_point}
                </div>
                <div className="font-mono text-[9px] text-text-3">
                  {d.device} ({d.fs_type})
                </div>
              </div>
              <div className={`p-2 rounded-lg bg-surface border ${colors.border} shadow-inner ${colors.icon}`}>
                <HardDrive className="w-3.5 h-3.5" />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between items-baseline font-mono text-[10px]">
                <span className="text-text-3 font-semibold">
                  {formatBytes(d.used_bytes)} / {formatBytes(d.total_bytes)}
                </span>
                <span className={`font-bold ${colors.text}`}>
                  {d.percent.toFixed(0)}%
                </span>
              </div>

              <div className="w-full bg-surface-2 rounded-full h-2 overflow-hidden border border-border shadow-inner">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${colors.bar}`}
                  style={{ width: `${d.percent}%` }}
                />
              </div>

              {/* Estimation row */}
              {d.days_left !== undefined && (
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className={`font-semibold ${colors.text}`}>
                    {daysLabel
                      ? d.days_left !== null
                        ? `⏱ ${daysLabel}`
                        : '—'
                      : ''}
                  </span>
                  {d.growth_gb_per_day !== undefined && d.growth_gb_per_day !== null && (
                    <span className="text-text-3 flex items-center gap-1">
                      {growthPositive
                        ? <TrendingUp className="w-3 h-3" />
                        : <TrendingDown className="w-3 h-3" />}
                      {d.growth_gb_per_day.toFixed(2)} {t('metrics.disk.growth_gb_day')}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
