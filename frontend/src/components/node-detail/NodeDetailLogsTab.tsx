import React, { useEffect, useRef } from 'react';
import { RefreshCw } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { ServiceRecord } from './types';

export const NodeDetailLogsTab: React.FC<{
  logs: string;
  loading: boolean;
  logsService: string;
  logsLimit: number;
  logsAutoScroll: boolean;
  services: ServiceRecord[];
  onServiceChange: (value: string) => void;
  onLimitChange: (value: number) => void;
  onAutoScrollChange: (value: boolean) => void;
  onRefresh: () => void;
}> = ({
  logs,
  loading,
  logsService,
  logsLimit,
  logsAutoScroll,
  services,
  onServiceChange,
  onLimitChange,
  onAutoScrollChange,
  onRefresh,
}) => {
  const { t } = useLocale();
  const consoleRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logsAutoScroll && consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs, logsAutoScroll]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg font-interface text-xs select-none">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-text-3 font-semibold uppercase tracking-wider text-[10px]">{t('node_detail.logs_target_label')}</span>
            <select
              value={logsService}
              onChange={(e) => onServiceChange(e.target.value)}
              className="bg-surface-2 border border-border rounded px-2.5 py-1 focus:outline-none text-text-2 font-semibold"
            >
              <option value="">{t('node_detail.logs_target_global')}</option>
              {services.map((srv) => (
                <option key={srv.name} value={srv.name}>{srv.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-text-3 font-semibold uppercase tracking-wider text-[10px]">{t('node_detail.logs_lines_label')}</span>
            <select
              value={logsLimit}
              onChange={(e) => onLimitChange(Number(e.target.value))}
              className="bg-surface-2 border border-border rounded px-2.5 py-1 focus:outline-none text-text-2 font-semibold"
            >
              <option value="50">{t('node_detail.logs_lines_50')}</option>
              <option value="100">{t('node_detail.logs_lines_100')}</option>
              <option value="250">{t('node_detail.logs_lines_250')}</option>
            </select>
          </div>

          <label className="flex items-center gap-1.5 text-text-2 cursor-pointer font-semibold">
            <input
              type="checkbox"
              checked={logsAutoScroll}
              onChange={(e) => onAutoScrollChange(e.target.checked)}
              className="rounded bg-surface-2 border-border accent-accent"
            />
            <span>{t('node_detail.logs_auto_scroll')}</span>
          </label>
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1.5 rounded hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer transition-colors ml-auto"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="relative">
        {loading && (
          <div className="absolute inset-0 bg-surface/50 backdrop-blur-xs flex items-center justify-center z-10 rounded-lg">
            <Spinner size="sm" />
          </div>
        )}
        <div
          ref={consoleRef}
          className="font-mono text-[10.5px] leading-relaxed p-5 bg-black text-text-2 border border-border rounded-lg h-[460px] overflow-y-auto whitespace-pre-wrap select-text scrollbar-thin shadow-inner"
        >
          {logs || t('node_detail.logs_empty')}
        </div>
      </div>
    </div>
  );
};
