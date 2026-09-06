import React, { useState, useCallback } from 'react';
import { Search, X, Copy, Download, Check } from 'lucide-react';
import { useLocale } from '../../i18n';

export interface LogToolbarProps {
  logsLimit: number;
  logsAutoScroll: boolean;
  loading: boolean;
  logs: string;
  searchTerm: string;
  searchMatchCount: number;
  onLimitChange: (value: number) => void;
  onAutoScrollChange: (value: boolean) => void;
  onSearchChange: (term: string) => void;
}

export const LogToolbar: React.FC<LogToolbarProps> = ({
  logsLimit,
  logsAutoScroll,
  logs,
  searchTerm,
  searchMatchCount,
  onLimitChange,
  onAutoScrollChange,
  onSearchChange,
}) => {
  const { t } = useLocale();
  const [searchOpen, setSearchOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (!logs) return;
    try {
      await navigator.clipboard.writeText(logs);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available
    }
  }, [logs]);

  const handleDownload = useCallback(() => {
    if (!logs) return;
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vigile-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.log`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [logs]);

  const handleToggleSearch = useCallback(() => {
    setSearchOpen((v) => {
      if (v) onSearchChange('');
      return !v;
    });
  }, [onSearchChange]);

  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-surface border border-border rounded-lg font-interface text-xs select-none">
      {/* Lines selector */}
      <div className="flex items-center gap-1.5">
        <span className="text-text-3 font-semibold uppercase tracking-wider text-[10px]">
          {t('node_detail.logs_lines_label')}
        </span>
        <select
          value={logsLimit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
          className="bg-surface-2 border border-border rounded px-2 py-1 focus:outline-none text-text-2 font-semibold text-[11px]"
        >
          <option value="50">{t('node_detail.logs_lines_50')}</option>
          <option value="100">{t('node_detail.logs_lines_100')}</option>
          <option value="250">{t('node_detail.logs_lines_250')}</option>
          <option value="500">{t('node_detail.logs_lines_500')}</option>
        </select>
      </div>

      {/* Separator */}
      <div className="w-px h-5 bg-border" />

      {/* Auto-scroll */}
      <label className="flex items-center gap-1.5 text-text-2 cursor-pointer font-semibold text-[11px]">
        <input
          type="checkbox"
          checked={logsAutoScroll}
          onChange={(e) => onAutoScrollChange(e.target.checked)}
          className="rounded bg-surface-2 border-border accent-accent"
        />
        <span>{t('node_detail.logs_auto_scroll')}</span>
      </label>

      {/* Separator */}
      <div className="w-px h-5 bg-border" />

      {/* Search toggle + inline input */}
      <div className="flex items-center gap-1.5">
        <button
          onClick={handleToggleSearch}
          className={`p-1.5 rounded cursor-pointer transition-colors ${
            searchOpen
              ? 'bg-accent/15 text-accent'
              : 'text-text-2 hover:text-text-1 hover:bg-surface-2'
          }`}
          title={t('node_detail.logs_search_placeholder')}
        >
          <Search className="w-3.5 h-3.5" />
        </button>
        {searchOpen && (
          <div className="flex items-center gap-1.5 animate-fade-in">
            <div className="relative">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder={t('node_detail.logs_search_placeholder')}
                autoFocus
                className="bg-surface-2 border border-border rounded pl-2 pr-6 py-1 focus:outline-none text-text-1 font-mono text-[11px] w-44 placeholder:text-text-3"
              />
              {searchTerm && (
                <button
                  onClick={() => onSearchChange('')}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-surface-3 text-text-3 hover:text-text-1 cursor-pointer transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            {searchTerm && (
              <span className="text-[10px] text-text-3 font-semibold tabular-nums whitespace-nowrap">
                {t('node_detail.logs_search_matches', { count: String(searchMatchCount) })}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Right side: copy + download */}
      <div className="flex items-center gap-1 ml-auto">
        {/* Copy */}
        <button
          onClick={() => void handleCopy()}
          disabled={!logs}
          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold text-text-2 hover:text-text-1 hover:bg-surface-2 cursor-pointer transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          title={t('node_detail.logs_copy')}
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-severity-ok" />
              <span className="text-severity-ok">{t('node_detail.logs_copied')}</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{t('node_detail.logs_copy')}</span>
            </>
          )}
        </button>

        {/* Download */}
        <button
          onClick={handleDownload}
          disabled={!logs}
          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-semibold text-text-2 hover:text-text-1 hover:bg-surface-2 cursor-pointer transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          title={t('node_detail.logs_download')}
        >
          <Download className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{t('node_detail.logs_download')}</span>
        </button>
      </div>
    </div>
  );
};
