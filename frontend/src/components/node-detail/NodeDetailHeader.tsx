import React from 'react';
import { useNavigate } from 'react-router';
import { Cpu, ArrowLeft, Calendar, Monitor, HardDrive, Tag } from 'lucide-react';
import { StatusDot } from '../primitives/StatusDot';
import { MetricPill } from '../primitives/MetricPill';
import { TimeAgo } from '../primitives/TimeAgo';
import { Badge } from '../primitives/Badge';
import { useLocale } from '../../i18n';
import type { NodeRecord, PerTypeReadiness } from './types';

export const NodeDetailHeader: React.FC<{ node: NodeRecord; observationReady?: boolean; perTypeReadiness?: PerTypeReadiness }> = ({ node, observationReady = true, perTypeReadiness }) => {
  const { t } = useLocale();
  const navigate = useNavigate();

  let isLearning = !observationReady;
  let learningPercent = 0;

  if (perTypeReadiness) {
    const { cpu, ram, disk, profile } = perTypeReadiness;
    const readyCount = [cpu, ram, disk, profile].filter((t) => t.ready).length;
    isLearning = readyCount < 4;
    learningPercent = Math.round((readyCount / 4) * 100);
  }

  return (
    <>
      <button
        onClick={() => navigate('/')}
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-surface hover:bg-surface-2 border border-border text-[10px] rounded font-interface font-bold uppercase tracking-widest text-text-2 hover:text-text-1 cursor-pointer transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>{t('node_detail.back_button')}</span>
      </button>

      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 p-4 sm:p-6 rounded-xl border border-border bg-surface relative overflow-hidden shadow">
        <div className="flex items-start sm:items-center gap-3 sm:gap-4 z-10 min-w-0">
          <div className="w-10 h-10 sm:w-12 sm:h-12 bg-accent-muted border border-accent/20 rounded-xl flex items-center justify-center text-accent shrink-0 mt-0.5 sm:mt-0">
            <Cpu className="w-5 h-5 sm:w-6 sm:h-6 text-accent animate-pulse" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <StatusDot state={node.state} />
              <h1 className="font-interface text-base sm:text-lg font-bold text-text-1 truncate">
                {node.name}
              </h1>
              <Badge severity={node.online ? 'ok' : 'offline'} className="text-[8px] px-1 py-0" />
              {isLearning && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-[8px] font-mono border border-amber-500/20 animate-pulse">
                  🔄 Apprentissage {perTypeReadiness ? `${learningPercent}%` : ''}
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 sm:gap-3 mt-2">
              {/* Enrolled Chip */}
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gradient-to-r from-surface-2/90 to-surface-3/50 border border-l-2 border-l-accent/40 border-border/60 text-text-2 text-[11px] font-sans font-medium whitespace-nowrap shadow-2xs hover:bg-surface-3/70 hover:border-border-strong hover:shadow-[0_2px_8px_rgba(245,158,11,0.08)] transition-all duration-200">
                <Calendar className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-accent shrink-0" />
                <span className="text-text-3 font-normal">{t('node_detail.enrolled_chip_prefix', { defaultValue: 'Enregistré' })}</span>
                <TimeAgo timestamp={node.enrolled_at} className="font-semibold text-text-1" />
              </div>

              {/* OS & Arch Chip */}
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gradient-to-r from-surface-2/90 to-surface-3/50 border border-l-2 border-l-accent/40 border-border/60 text-text-2 text-[11px] font-sans font-medium whitespace-nowrap shadow-2xs hover:bg-surface-3/70 hover:border-border-strong hover:shadow-[0_2px_8px_rgba(245,158,11,0.08)] transition-all duration-200">
                <Monitor className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-accent shrink-0" />
                <span className="text-text-1 font-semibold">
                  {node.os || t('node_detail.os_default')}
                  <span className="text-text-3 font-normal text-[10px] ml-1">({node.arch || t('node_detail.arch_default')})</span>
                </span>
              </div>

              {/* Hostname Chip */}
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gradient-to-r from-surface-2/90 to-surface-3/50 border border-l-2 border-l-accent/40 border-border/60 text-text-2 text-[11px] font-sans font-medium whitespace-nowrap shadow-2xs hover:bg-surface-3/70 hover:border-border-strong hover:shadow-[0_2px_8px_rgba(245,158,11,0.08)] transition-all duration-200">
                <HardDrive className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-accent shrink-0" />
                <span className="text-text-3 font-normal">{t('node_detail.hostname_chip_prefix', { defaultValue: 'Host:' })}</span>
                <span className="font-mono text-text-1 font-semibold">{node.hostname || t('common.unknown')}</span>
              </div>

              {/* Version Chip */}
              {(node.worker_version || node.version) && (
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gradient-to-r from-accent-muted/25 to-accent-muted/10 border border-l-2 border-l-accent/60 border-accent/20 text-accent text-[11px] font-mono font-medium whitespace-nowrap shadow-2xs hover:bg-accent-muted/35 hover:border-accent/40 hover:shadow-[0_2px_8px_rgba(245,158,11,0.10)] transition-all duration-200" title="Version déclarée par le binaire Go du Worker">
                  <Tag className="w-3.5 h-3.5 shrink-0" />
                  <span>Worker v{node.worker_version || node.version}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0 z-10 w-full xl:w-auto justify-start xl:justify-end">
          {node.online && (
            <MetricPill
              cpu={node.cpu_percent}
              mem={node.memory_percent}
              disk={node.disk_percent}
              uptime={node.uptime_seconds}
              className="text-xs py-1 px-3.5"
            />
          )}
        </div>
      </div>
    </>
  );
};
