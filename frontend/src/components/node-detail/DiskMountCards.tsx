import React, { useState } from 'react';
import { HardDrive, TrendingUp, TrendingDown, Wifi, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useLocale } from '../../i18n';
import type { DiskMount } from './types';

interface DiskMountCardsProps {
  disks: DiskMount[];
  onNavigateToTreemap?: () => void;
}

const TIER_COLORS = {
  critical: {
    badge: 'bg-red-500/10 text-severity-critical border-red-500/30',
    bar: 'bg-severity-critical',
    text: 'text-severity-critical',
    border: 'border-red-500/20',
  },
  warning: {
    badge: 'bg-amber-500/10 text-severity-warning border-amber-500/30',
    bar: 'bg-severity-warning',
    text: 'text-severity-warning',
    border: 'border-amber-500/20',
  },
  elevated: {
    badge: 'bg-amber-500/10 text-zone-elevated border-amber-500/30',
    bar: 'bg-zone-elevated',
    text: 'text-zone-elevated',
    border: 'border-amber-500/20',
  },
  ok: {
    badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    bar: 'bg-emerald-500',
    text: 'text-emerald-400',
    border: 'border-emerald-500/10',
  },
} as const;

function isNetworkMount(d: DiskMount): boolean {
  const fs = (d.fs_type || '').toLowerCase();
  return ['nfs', 'nfs4', 'cifs', 'smb', 'sshfs', 'fuse.sshfs', 'ceph', 'glusterfs'].some((netFs) => fs.includes(netFs));
}

function formatDaysLeft(
  days: number | null,
  t: (key: string, vars?: Record<string, unknown>) => string,
): string | null {
  if (days === null) return null;
  if (days < 1) return t('metrics.disk.saturation.today', { defaultValue: 'Rempli aujourd\'hui' });
  if (days === 1) return t('metrics.disk.saturation.day', { defaultValue: '~1 jour restant' });
  if (days < 30) return `~${days} jours restants au rythme actuel`;
  if (days < 365) return `~${Math.round(days / 30)} mois restants`;
  return `~${Math.round(days / 365)} ans restants`;
}

export const DiskMountCards: React.FC<DiskMountCardsProps> = ({ disks, onNavigateToTreemap }) => {
  const { t } = useLocale();
  const navigate = useNavigate();
  const [selectedMountTrend, setSelectedMountTrend] = useState<string | null>(null);

  if (disks.length === 0) return null;

  const handleTreemapClick = () => {
    if (onNavigateToTreemap) {
      onNavigateToTreemap();
    } else {
      navigate('?tab=disk');
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
        {disks.map((d, idx) => {
          const isNet = isNetworkMount(d);
          const tierKey = d.percent >= 95 ? 'critical' : d.percent >= 85 ? 'warning' : d.percent >= 75 ? 'elevated' : 'ok';
          const tier = TIER_COLORS[tierKey];

          const daysLabel = formatDaysLeft(d.days_left ?? null, t);
          const growthPositive = d.growth_gb_per_day !== null && d.growth_gb_per_day !== undefined && d.growth_gb_per_day > 0;
          const usedGb = (d.used_bytes / (1024 * 1024 * 1024)).toFixed(1);
          const totalGb = (d.total_bytes / (1024 * 1024 * 1024)).toFixed(1);

          return (
            <div
              key={idx}
              className={`bg-surface/50 border ${tier.border} rounded-2xl p-4 flex flex-col justify-between gap-4 backdrop-blur-sm transition-all duration-300 hover:border-accent/35 shadow-sm`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-0.5 truncate">
                  <div className="flex items-center gap-2">
                    <span className="font-interface font-black text-xs text-text-1 truncate" title={d.mount_point}>
                      {d.mount_point}
                    </span>
                    {isNet && (
                      <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 flex items-center gap-1">
                        <Wifi className="w-2.5 h-2.5" />
                        Réseau
                      </span>
                    )}
                  </div>
                  <div className="font-mono text-[9px] text-text-3 truncate" title={d.device}>
                    {d.device} ({d.fs_type})
                  </div>
                </div>
                <div className={`p-2 rounded-lg bg-surface border ${tier.border} shadow-inner`}>
                  <HardDrive className={`w-3.5 h-3.5 ${tier.text}`} />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-baseline font-mono text-[10px]">
                  <span className="text-text-1 font-bold text-xs">
                    {usedGb} Go <span className="text-text-3 font-normal">/ {totalGb} Go</span>
                  </span>
                  <span className={`font-bold text-xs ${tier.text}`}>
                    {d.percent.toFixed(1)}%
                  </span>
                </div>

                <div className="w-full bg-surface-2 rounded-full h-2 overflow-hidden border border-border shadow-inner">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${tier.bar}`}
                    style={{ width: `${Math.min(100, Math.max(0, d.percent))}%` }}
                  />
                </div>

                {daysLabel && (
                  <div className="font-mono text-[10px] text-text-2 flex items-center justify-between pt-1">
                    <span className="font-semibold text-text-1">
                      ⏱ {daysLabel}
                    </span>
                    {d.growth_gb_per_day != null && (
                      <span className="text-text-3 flex items-center gap-1 text-[9px]">
                        {growthPositive ? <TrendingUp className="w-3 h-3 text-amber-400" /> : <TrendingDown className="w-3 h-3 text-emerald-400" />}
                        {Math.abs(d.growth_gb_per_day) < 0.1 && d.growth_gb_per_day !== 0
                          ? `${d.growth_gb_per_day > 0 ? '+' : ''}${Math.round(d.growth_gb_per_day * 1024)} Mo/j`
                          : `${d.growth_gb_per_day > 0 ? '+' : ''}${d.growth_gb_per_day.toFixed(2)} Go/j`}
                      </span>
                    )}
                  </div>
                )}

                <div className="flex items-center justify-between pt-2 border-t border-border/50">
                  <button
                    onClick={() => setSelectedMountTrend(selectedMountTrend === d.mount_point ? null : d.mount_point)}
                    className="text-[9px] font-interface font-bold uppercase text-text-3 hover:text-text-1 transition-colors flex items-center gap-1 cursor-pointer"
                  >
                    <TrendingUp className="w-3 h-3" />
                    {selectedMountTrend === d.mount_point ? 'Masquer Tendance' : 'Vue Tendance'}
                  </button>

                  <button
                    onClick={handleTreemapClick}
                    className="text-[9px] font-interface font-bold uppercase text-accent hover:underline flex items-center gap-0.5 cursor-pointer"
                  >
                    Treemap <ChevronRight className="w-3 h-3" />
                  </button>
                </div>

                {/* Expansion Vue Tendance */}
                {selectedMountTrend === d.mount_point && (
                  <div className="p-3 bg-surface-2/60 border border-border rounded-xl space-y-2 animate-fade-in mt-2 font-mono text-[10px]">
                    <div className="flex justify-between items-center text-text-3 uppercase text-[8px] font-bold">
                      <span>Projection d'extrapolation (Go)</span>
                      <span className="text-accent">{d.growth_gb_per_day?.toFixed(2) || '0'} Go / jour</span>
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between">
                        <span className="text-text-3">Actuel :</span>
                        <span className="font-bold text-text-1">{usedGb} Go</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-3">+7 jours :</span>
                        <span className="font-bold text-text-2">
                          {(parseFloat(usedGb) + (d.growth_gb_per_day || 0) * 7).toFixed(1)} Go
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-3">+30 jours :</span>
                        <span className="font-bold text-amber-400">
                          {(parseFloat(usedGb) + (d.growth_gb_per_day || 0) * 30).toFixed(1)} Go
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

