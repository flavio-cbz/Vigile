import React, { useState, useEffect, useRef } from 'react';
import { Search, X, FileText, Cpu, Box, AlertCircle } from 'lucide-react';
import type { LogSourceItemRecord } from './types';
import { useLocale } from '../../i18n';

interface LogSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  sources: LogSourceItemRecord[];
  activeSource: string;
  onSelectSource: (source: LogSourceItemRecord | null) => void;
}

export const LogSourceModal: React.FC<LogSourceModalProps> = ({
  isOpen,
  onClose,
  sources,
  activeSource,
  onSelectSource,
}) => {
  const { t } = useLocale();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<'all' | 'files' | 'services' | 'docker'>('all');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setSearch('');
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
      if ((e.key === 's' || e.key === 'S') && !isOpen && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const filteredSources = sources.filter((s) => {
    const matchesCat = category === 'all' || s.category === category;
    const q = search.toLowerCase().trim();
    const matchesQuery = !q || s.name.toLowerCase().includes(q) || (s.path && s.path.toLowerCase().includes(q));
    return matchesCat && matchesQuery;
  });

  const filesCount = sources.filter((s) => s.category === 'files').length;
  const servicesCount = sources.filter((s) => s.category === 'services').length;
  const dockerCount = sources.filter((s) => s.category === 'docker').length;

  const formatSize = (bytes?: number) => {
    if (!bytes) return null;
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${bytes} B`;
  };

  const getSourceIcon = (cat: string) => {
    switch (cat) {
      case 'services': return <Cpu className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
      case 'docker': return <Box className="w-3.5 h-3.5 text-cyan-400 shrink-0" />;
      default: return <FileText className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
    }
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-start justify-center pt-20 px-4 animate-in fade-in duration-100"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-surface border border-border rounded-xl w-full max-w-2xl max-h-[75vh] flex flex-col shadow-2xl overflow-hidden font-interface"
      >
        {/* Search header */}
        <div className="p-3.5 border-b border-border flex items-center gap-3 bg-surface-2">
          <Search className="w-4 h-4 text-text-3 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('node_detail.logs_search_sources_placeholder') || 'Rechercher une source (/var/log, service systemd, docker)...'}
            className="flex-1 bg-transparent border-none outline-none text-text-1 text-sm placeholder:text-text-3 font-mono"
          />
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-text-3 bg-surface border border-border px-1.5 py-0.5 rounded">
              ESC
            </span>
            <button
              onClick={onClose}
              className="p-1 text-text-3 hover:text-text-1 rounded hover:bg-surface-3 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Categories */}
        <div className="flex items-center gap-1.5 px-3.5 py-2 border-b border-border bg-surface text-xs select-none">
          <button
            onClick={() => setCategory('all')}
            className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
              category === 'all' ? 'bg-surface-2 text-text-1 font-semibold border border-border' : 'text-text-3 hover:text-text-2'
            }`}
          >
            {t('common.all') || 'Tous'} ({sources.length})
          </button>
          <button
            onClick={() => setCategory('files')}
            className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
              category === 'files' ? 'bg-surface-2 text-text-1 font-semibold border border-border' : 'text-text-3 hover:text-text-2'
            }`}
          >
            📁 /var/log ({filesCount})
          </button>
          <button
            onClick={() => setCategory('services')}
            className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
              category === 'services' ? 'bg-surface-2 text-text-1 font-semibold border border-border' : 'text-text-3 hover:text-text-2'
            }`}
          >
            ⚙️ Systemd ({servicesCount})
          </button>
          <button
            onClick={() => setCategory('docker')}
            className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
              category === 'docker' ? 'bg-surface-2 text-text-1 font-semibold border border-border' : 'text-text-3 hover:text-text-2'
            }`}
          >
            🐳 Docker ({dockerCount})
          </button>
        </div>

        {/* Sources list */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin">
          {/* Global journal shortcut */}
          <div
            onClick={() => {
              onSelectSource(null);
              onClose();
            }}
            className={`flex items-center justify-between p-2.5 rounded-lg cursor-pointer transition-colors text-xs font-mono ${
              !activeSource ? 'bg-accent/15 border border-accent/30 text-accent font-semibold' : 'hover:bg-surface-2 text-text-2'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Cpu className="w-3.5 h-3.5 text-accent" />
              <span>journald (global)</span>
            </div>
            <span className="text-[10px] text-text-3">systemd default</span>
          </div>

          {filteredSources.map((s) => {
            const isSelected = activeSource === s.id || activeSource === s.name;
            return (
              <div
                key={s.id}
                onClick={() => {
                  onSelectSource(s);
                  onClose();
                }}
                className={`flex items-center justify-between p-2.5 rounded-lg cursor-pointer transition-colors text-xs font-mono ${
                  isSelected ? 'bg-accent/15 border border-accent/30 text-accent font-semibold' : 'hover:bg-surface-2 text-text-2'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {getSourceIcon(s.category)}
                  <span className="truncate">{s.name}</span>
                  {s.error_count > 0 && (
                    <span className="inline-flex items-center gap-1 text-[10px] text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded border border-red-500/20 shrink-0">
                      <AlertCircle className="w-2.5 h-2.5" />
                      {s.error_count}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 text-[11px] text-text-3 shrink-0 ml-2">
                  {s.size_bytes !== undefined && s.size_bytes !== null && (
                    <span>{formatSize(s.size_bytes)}</span>
                  )}
                  {s.status && <span className="text-[10.5px]">{s.status}</span>}
                </div>
              </div>
            );
          })}

          {filteredSources.length === 0 && (
            <div className="py-12 text-center text-text-3 text-xs">
              {t('common.no_results') || 'Aucune source correspondante'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
