import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';
import type { LogEntryRecord } from './types';
import { useLocale } from '../../i18n';

interface LogConsoleProps {
  entries: LogEntryRecord[];
  rawText: string;
  loading: boolean;
  filterQuery: string;
  severityFilter: 'all' | 'error' | 'warn' | 'info';
  autoScroll: boolean;
}

export const LogConsole: React.FC<LogConsoleProps> = ({
  entries,
  rawText,
  loading,
  filterQuery,
  severityFilter,
  autoScroll,
}) => {
  const { t } = useLocale();
  const [expandedIndices, setExpandedIndices] = useState<Set<number>>(new Set());
  const [copied, setCopied] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Parse raw text into lines if entries array is empty (fallback)
  const displayEntries: LogEntryRecord[] = entries.length > 0
    ? entries
    : rawText
        ? rawText.split('\n').filter(Boolean).map((line, idx) => ({
            timestamp: Date.now() / 1000,
            time_str: line.substring(0, 15),
            level: /error|fail|crit/i.test(line) ? 'error' : (/warn/i.test(line) ? 'warn' : 'info'),
            unit: 'system',
            message: line,
          }))
        : [];

  const filteredEntries = displayEntries.filter((item) => {
    // Severity filter
    if (severityFilter === 'error' && item.level !== 'error') return false;
    if (severityFilter === 'warn' && item.level !== 'warn' && item.level !== 'error') return false;
    if (severityFilter === 'info' && item.level !== 'info') return false;

    // Text search query
    if (filterQuery) {
      const q = filterQuery.toLowerCase();
      const matchMsg = item.message.toLowerCase().includes(q);
      const matchUnit = item.unit.toLowerCase().includes(q);
      return matchMsg || matchUnit;
    }

    return true;
  });

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredEntries.length, autoScroll]);

  const toggleExpand = (idx: number) => {
    setExpandedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const handleCopyLogs = () => {
    const text = filteredEntries.map((e) => `${e.time_str} [${e.level.toUpperCase()}] ${e.unit}: ${e.message}`).join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getLevelBadgeClass = (lvl: string) => {
    switch (lvl) {
      case 'error': return 'text-red-400 bg-red-500/15 border-red-500/30';
      case 'warn': return 'text-amber-400 bg-amber-500/15 border-amber-500/30';
      case 'debug': return 'text-purple-400 bg-purple-500/15 border-purple-500/30';
      default: return 'text-text-3 bg-white/5 border-border';
    }
  };

  return (
    <div className="bg-surface border border-border rounded-lg overflow-hidden flex flex-col font-interface shadow-inner">
      {/* Stream sub-bar */}
      <div className="px-4 py-2 bg-surface-2 border-b border-border flex items-center justify-between text-xs text-text-3 font-mono">
        <span>
          {t('node_detail.logs_count_showing', { count: filteredEntries.length, total: displayEntries.length }) ||
            `${filteredEntries.length} lignes affichées`}
        </span>
        <button
          onClick={handleCopyLogs}
          className="inline-flex items-center gap-1.5 text-text-2 hover:text-text-1 cursor-pointer transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? (t('common.copied') || 'Copié !') : (t('common.copy') || 'Copier')}</span>
        </button>
      </div>

      {/* Log Console Container */}
      <div
        ref={containerRef}
        className="max-h-[520px] min-h-[300px] overflow-y-auto overflow-x-auto scrollbar-thin bg-surface-2/70 select-text"
      >
        {filteredEntries.length === 0 ? (
          <div className="py-20 text-center text-text-3 font-mono text-xs">
            {loading ? 'Chargement des logs...' : (t('node_detail.logs_empty') || 'Aucun log pour cette sélection')}
          </div>
        ) : (
          <table className="w-full border-collapse font-mono text-[11.5px] leading-relaxed">
            <tbody>
              {filteredEntries.map((entry, idx) => {
                const isExpanded = expandedIndices.has(idx);
                const isError = entry.level === 'error';
                const isWarn = entry.level === 'warn';

                return (
                  <React.Fragment key={idx}>
                    <tr
                      onClick={() => toggleExpand(idx)}
                      className={`border-b border-border/40 hover:bg-surface-3/60 transition-colors cursor-pointer ${
                        isError
                          ? 'bg-red-500/8 border-l-2 border-l-red-500 hover:bg-red-500/12'
                          : isWarn
                          ? 'bg-amber-500/8 border-l-2 border-l-amber-500 hover:bg-amber-500/12'
                          : ''
                      }`}
                    >
                      {/* Line index & expand chevron */}
                      <td className="py-1.5 pl-3 pr-1 text-right text-text-3 text-[10px] w-10 select-none">
                        <span className="inline-flex items-center gap-1">
                          {isExpanded ? <ChevronDown className="w-2.5 h-2.5 text-text-2" /> : <ChevronRight className="w-2.5 h-2.5 opacity-40" />}
                          {idx + 1}
                        </span>
                      </td>

                      {/* Timestamp */}
                      <td className="py-1.5 px-2 text-text-3 whitespace-nowrap w-24 text-[11px]">
                        {entry.time_str || '-'}
                      </td>

                      {/* Level badge */}
                      <td className="py-1.5 px-1.5 w-12 text-center select-none">
                        <span className={`px-1.5 py-0.5 rounded text-[9.5px] font-bold border ${getLevelBadgeClass(entry.level)}`}>
                          {entry.level.toUpperCase().substring(0, 4)}
                        </span>
                      </td>

                      {/* Unit / Service */}
                      <td className="py-1.5 px-2 text-text-2 font-semibold whitespace-nowrap max-w-[130px] truncate text-[11px]">
                        {entry.unit}
                      </td>

                      {/* Message */}
                      <td className={`py-1.5 pr-4 pl-2 break-all ${isError ? 'text-red-200' : isWarn ? 'text-amber-200' : 'text-text-1'}`}>
                        {entry.message}
                      </td>
                    </tr>

                    {/* Expandable RAW Metadata Inspector */}
                    {isExpanded && (
                      <tr className="bg-surface-3/90 border-b border-border">
                        <td colSpan={5} className="p-3 pl-12">
                          <div className="bg-surface border border-border rounded p-3 text-[11px] space-y-2">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-text-3">
                              Détails & Métadonnées
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                              <div><span className="text-text-3">Niveau :</span> <span className="text-text-1 font-semibold">{entry.level}</span></div>
                              <div><span className="text-text-3">Source/Unité :</span> <span className="text-text-1 font-semibold">{entry.unit}</span></div>
                              <div><span className="text-text-3">Horodatage :</span> <span className="text-text-1">{entry.time_str}</span></div>
                            </div>
                            {entry.raw && (
                              <div className="mt-2 pt-2 border-t border-border/60">
                                <div className="text-[10px] text-text-3 font-semibold mb-1">Payload JSON brut :</div>
                                <pre className="p-2 bg-surface-2 rounded text-[10px] overflow-x-auto text-text-2 font-mono">
                                  {JSON.stringify(entry.raw, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
