import React from 'react';
import { HardDrive } from 'lucide-react';
import type { DiskMount } from './types';

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

const PROGRESS_COLORS = {
  crit: { bar: 'bg-severity-critical', text: 'text-severity-critical', border: 'border-red-500/10' },
  warn: { bar: 'bg-severity-warning', text: 'text-severity-warning', border: 'border-amber-500/10' },
  ok: { bar: 'bg-accent', text: 'text-accent', border: 'border-amber-500/5' },
} as const;

export const DiskMountCards: React.FC<DiskMountCardsProps> = ({ disks }) => {
  if (disks.length === 0) return null;

  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
      {disks.map((d, idx) => {
        const warningState = d.percent > 85 ? 'crit' : d.percent > 70 ? 'warn' : 'ok';
        const colors = PROGRESS_COLORS[warningState];

        return (
          <div key={idx} className="bg-surface/50 border border-border rounded-2xl p-4 flex flex-col justify-between gap-4 backdrop-blur-sm transition-all duration-300 hover:border-accent/35 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-0.5 truncate">
                <div className="font-interface font-black text-xs text-text-1 truncate" title={d.mount_point}>
                  {d.mount_point}
                </div>
                <div className="font-mono text-[9px] text-text-3">
                  {d.device} ({d.fs_type})
                </div>
              </div>
              <div className="p-2 rounded-lg bg-surface border border-border shadow-inner text-text-3 shrink-0">
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
            </div>
          </div>
        );
      })}
    </div>
  );
};
