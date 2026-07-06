import React from 'react';
import { useNavigate } from 'react-router';
import { Cpu, ArrowLeft, Calendar } from 'lucide-react';
import { StatusDot } from '../primitives/StatusDot';
import { MetricPill } from '../primitives/MetricPill';
import { TimeAgo } from '../primitives/TimeAgo';
import { Badge } from '../primitives/Badge';
import { useLocale } from '../../i18n';
import type { NodeRecord } from './types';

export const NodeDetailHeader: React.FC<{ node: NodeRecord }> = ({ node }) => {
  const { t } = useLocale();
  const navigate = useNavigate();

  return (
    <>
      <button
        onClick={() => navigate('/')}
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-surface hover:bg-surface-2 border border-border text-[10px] rounded font-interface font-bold uppercase tracking-widest text-text-2 hover:text-text-1 cursor-pointer transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>{t('node_detail.back_button')}</span>
      </button>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-xl border border-border bg-surface relative overflow-hidden shadow">
        <div className="flex items-center gap-4 z-10 min-w-0">
          <div className="w-12 h-12 bg-accent-muted border border-accent/20 rounded-xl flex items-center justify-center text-accent">
            <Cpu className="w-6 h-6 text-accent animate-pulse" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <StatusDot state={node.state} />
              <h1 className="font-interface text-lg font-bold text-text-1 truncate">
                {node.name}
              </h1>
              <Badge severity={node.online ? 'ok' : 'offline'} className="text-[8px] px-1 py-0" />
            </div>

            <div className="flex items-center gap-3 text-text-3 text-[10px] font-mono mt-1">
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3 opacity-60" /> {t('node_detail.enrolled_label')} <TimeAgo timestamp={node.enrolled_at} />
              </span>
              <span>·</span>
              <span>{t('node_detail.os_label', { os: node.os || t('node_detail.os_default'), arch: node.arch || t('node_detail.arch_default') })}</span>
              <span>·</span>
              <span>{t('node_detail.hostname_label', { hostname: node.hostname || t('common.unknown') })}</span>
              {node.version && (
                <>
                  <span>·</span>
                  <span>{t('node_detail.version_label', { version: node.version })}</span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0 z-10">
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
