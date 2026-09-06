import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type {
  LogEntryRecord,
  LogSourceItemRecord,
  LogHistogramRecord,
} from './types';
import { LogTimeline } from './LogTimeline';
import { LogSourceBar } from './LogSourceBar';
import { LogSourceModal } from './LogSourceModal';
import { LogConsole } from './LogConsole';

export interface NodeDetailLogsTabProps {
  logs: string;
  logEntries?: LogEntryRecord[];
  loading: boolean;
  logsService: string;
  logsPath: string;
  logsLimit: number;
  logsSince?: string;
  logsUntil?: string;
  logsAutoScroll: boolean;
  logSources?: LogSourceItemRecord[];
  logHistogram?: LogHistogramRecord | null;
  loadingHistogram?: boolean;
  selectedBucketHour?: string | null;
  onSelectHour: (hour: string | null, since?: string, until?: string) => void;
  onServiceChange: (value: string) => void;
  onPathChange: (value: string) => void;
  onLogsPathChange?: (value: string) => void;
  onLimitChange: (value: number) => void;
  onAutoScrollChange: (value: boolean) => void;
  /** @deprecated B5 — polling 15s actif, bouton supprimé. Conservée pour compatibilité parent/tests. */
  onRefresh?: () => void;
  onRefreshSources?: () => void;
  logsError?: string | null;
  onRefreshHistogram?: () => void;
}

export const NodeDetailLogsTab: React.FC<NodeDetailLogsTabProps> = ({
  logs,
  logEntries = [],
  loading,
  logsService,
  logsPath,
  logsLimit,
  logsAutoScroll,
  logSources = [],
  logHistogram = null,
  loadingHistogram = false,
  selectedBucketHour = null,
  onSelectHour,
  onServiceChange,
  onPathChange,
  onLimitChange,
  onAutoScrollChange,
  logsError = null,
}) => {
  const { t } = useLocale();
  const [filterQuery, setFilterQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<'all' | 'error' | 'warn' | 'info'>('all');
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);

  const handleSelectSourceFromModal = (source: LogSourceItemRecord | null) => {
    if (!source) {
      onServiceChange('');
      onPathChange('');
    } else if (source.category === 'services' && source.unit) {
      onPathChange('');
      onServiceChange(source.unit);
    } else if (source.category === 'docker') {
      onPathChange('');
      onServiceChange(source.name);
    } else if (source.path) {
      onServiceChange('');
      onPathChange(source.path);
    }
  };

  const activeSourceId = logsService || logsPath;

  return (
    <div className="space-y-3 font-interface">
      {logsError && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs text-red-300">
          <div className="font-semibold">Erreur de lecture du log</div>
          <div className="mt-1 font-mono break-all text-red-200/80">{logsError}</div>
        </div>
      )}
      {/* 1. 24h Interactive Density Histogram */}
      <LogTimeline
        histogram={logHistogram}
        loading={loadingHistogram}
        selectedHour={selectedBucketHour}
        onSelectHour={onSelectHour}
      />

      {/* 2. Pinned Sources & Fuzzy Finder Trigger */}
      <LogSourceBar
        sources={logSources}
        activeService={logsService}
        activePath={logsPath}
        onSelectService={onServiceChange}
        onSelectPath={onPathChange}
        onOpenModal={() => setIsSourceModalOpen(true)}
      />

      {/* 3. Search & Control Hub Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-surface border border-border rounded-lg text-xs select-none">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-text-3 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            id="logs-filter-input"
            type="text"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder={t('node_detail.logs_filter_placeholder')}
            className="w-full bg-surface-2 border border-border rounded-md pl-8 pr-3 py-1.5 text-xs text-text-1 placeholder:text-text-3 font-mono outline-none focus:border-accent"
          />
        </div>

        {/* Severity filter buttons */}
        <div className="flex items-center gap-1 font-mono text-[11px]">
          <button
            onClick={() => setSeverityFilter('all')}
            className={`px-2.5 py-1 rounded transition-colors ${
              severityFilter === 'all'
                ? 'bg-surface-3 text-text-1 font-bold border border-text-3'
                : 'text-text-3 hover:text-text-2 border border-transparent'
            }`}
          >
            {t('common.all')}
          </button>
          <button
            onClick={() => setSeverityFilter('error')}
            className={`px-2.5 py-1 rounded transition-colors ${
              severityFilter === 'error'
                ? 'bg-red-500/20 text-red-400 font-bold border border-red-500/40'
                : 'text-text-3 hover:text-red-400 border border-transparent'
            }`}
          >
            ERR
          </button>
          <button
            onClick={() => setSeverityFilter('warn')}
            className={`px-2.5 py-1 rounded transition-colors ${
              severityFilter === 'warn'
                ? 'bg-amber-500/20 text-amber-400 font-bold border border-amber-500/40'
                : 'text-text-3 hover:text-amber-400 border border-transparent'
            }`}
          >
            WRN
          </button>
          <button
            onClick={() => setSeverityFilter('info')}
            className={`px-2.5 py-1 rounded transition-colors ${
              severityFilter === 'info'
                ? 'bg-blue-500/20 text-blue-400 font-bold border border-blue-500/40'
                : 'text-text-3 hover:text-blue-400 border border-transparent'
            }`}
          >
            INF
          </button>
        </div>

        {/* Lines Limit & Auto-scroll */}
        <div className="flex items-center gap-3 border-l border-border pl-3 text-text-2 text-xs">
          <select
            value={logsLimit}
            onChange={(e) => onLimitChange(Number(e.target.value))}
            className="bg-surface-2 border border-border rounded px-2 py-1 text-[11px] font-mono focus:outline-none cursor-pointer"
          >
            <option value="50">50 l</option>
            <option value="100">100 l</option>
            <option value="250">250 l</option>
            <option value="500">500 l</option>
          </select>

          <label className="flex items-center gap-1.5 text-text-2 cursor-pointer font-medium text-[11.5px]">
            <input
              type="checkbox"
              checked={logsAutoScroll}
              onChange={(e) => onAutoScrollChange(e.target.checked)}
              className="rounded bg-surface-2 border-border accent-accent"
            />
            <span className="hidden sm:inline">{t('node_detail.logs_auto_scroll')}</span>
          </label>

          {/* Live stream badge */}
          <div className="hidden md:inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/25 text-emerald-400 font-mono text-[10.5px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>LIVE</span>
          </div>
        </div>
      </div>

      {/* 4. Log Console with structured table and expandable raw inspector */}
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 bg-surface/50 backdrop-blur-xs flex items-center justify-center z-20 rounded-lg">
            <Spinner size="sm" />
          </div>
        )}
        <LogConsole
          entries={logEntries}
          rawText={logs}
          loading={loading}
          filterQuery={filterQuery}
          severityFilter={severityFilter}
          autoScroll={logsAutoScroll}
        />
      </div>

      {/* 5. Fuzzy Finder Modal */}
      <LogSourceModal
        isOpen={isSourceModalOpen}
        onClose={() => setIsSourceModalOpen(false)}
        sources={logSources}
        activeSource={activeSourceId}
        onSelectSource={handleSelectSourceFromModal}
      />
    </div>
  );
};
