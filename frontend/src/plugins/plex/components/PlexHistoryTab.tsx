import React, { useState } from 'react';
import { User, Tv, Search, ChevronLeft, ChevronRight, Film, Tv2 } from 'lucide-react';

export interface PlexWatchHistoryEntry {
  id: number;
  node_id: string;
  user: string;
  title: string;
  grandparent_title?: string;
  media_type: string;
  viewed_at: number;
  duration_watched_s: number;
  progress_percent: number;
  device?: string;
  quality?: string;
}

interface PlexHistoryTabProps {
  history: PlexWatchHistoryEntry[];
  total: number;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
  onSearchChange: (query: string, mediaType?: string) => void;
  isLoading?: boolean;
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0 min';
  const mins = Math.floor(seconds / 60);
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  if (hrs > 0) {
    return `${hrs}h ${remMins > 0 ? `${remMins}m` : ''}`;
  }
  return `${mins} min`;
}

function formatDate(timestamp: number): string {
  if (!timestamp) return 'Récemment';
  const date = new Date(timestamp * 1000);
  return date.toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const PlexHistoryTab: React.FC<PlexHistoryTabProps> = ({
  history,
  total,
  limit,
  offset,
  onPageChange,
  onSearchChange,
  isLoading = false,
}) => {
  const [query, setQuery] = useState('');
  const [mediaType, setMediaType] = useState<string>('');

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearchChange(query, mediaType);
  };

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="flex flex-col gap-4">
      {/* Search & Filter Header Bar */}
      <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-text-3 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              onSearchChange(e.target.value, mediaType);
            }}
            placeholder="Rechercher par utilisateur, titre, série..."
            className="w-full pl-9 pr-4 py-2 text-xs rounded-xl border border-border-strong/30 bg-surface-2/40 text-text-1 font-mono focus:outline-none focus:border-orange-500/50"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <select
            value={mediaType}
            onChange={(e) => {
              setMediaType(e.target.value);
              onSearchChange(query, e.target.value);
            }}
            className="px-3 py-2 text-xs rounded-xl border border-border-strong/30 bg-surface-2/40 text-text-1 font-mono focus:outline-none focus:border-orange-500/50 cursor-pointer"
          >
            <option value="">Tous les types</option>
            <option value="movie">Films</option>
            <option value="episode">Épisodes</option>
          </select>
        </div>
      </form>

      {/* History List */}
      {isLoading ? (
        <div className="text-center py-12 text-text-3 text-xs uppercase font-mono">
          Chargement de l'historique...
        </div>
      ) : history.length === 0 ? (
        <div className="text-center py-12 text-text-3 text-xs uppercase tracking-wider font-mono bg-surface-1/30 rounded-xl border border-border-strong/10">
          Aucune entrée dans l'historique de lecture
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {history.map((entry) => (
            <div
              key={entry.id}
              className="p-3.5 bg-surface-2/30 border border-border-strong/15 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-surface-2/50 transition-all"
            >
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="w-9 h-9 rounded-xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-500 shrink-0 font-mono font-bold text-xs">
                  {entry.media_type === 'episode' ? <Tv2 className="w-4 h-4" /> : <Film className="w-4 h-4" />}
                </div>

                <div className="min-w-0">
                  <div className="text-sm font-bold text-text-1 truncate">
                    {entry.grandparent_title ? `${entry.grandparent_title} - ` : ''}
                    {entry.title}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 mt-1 text-xs text-text-3 font-mono">
                    <span className="flex items-center gap-1 font-medium text-text-2">
                      <User className="w-3.5 h-3.5 text-orange-400" /> {entry.user}
                    </span>
                    {entry.device && (
                      <span className="flex items-center gap-1">
                        <Tv className="w-3.5 h-3.5 text-zinc-400" /> {entry.device}
                      </span>
                    )}
                    <span>•</span>
                    <span>{formatDate(entry.viewed_at)}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between sm:justify-end gap-4 shrink-0 font-mono text-xs">
                <div className="text-right">
                  <div className="text-text-1 font-bold">{formatDuration(entry.duration_watched_s)}</div>
                  <div className="text-[10px] text-text-3">Visionné à {Math.round(entry.progress_percent || 100)}%</div>
                </div>

                {entry.quality && (
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                      entry.quality.toLowerCase().includes('transcode')
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                        : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    }`}
                  >
                    {entry.quality}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-3 border-t border-border-strong/15 text-xs font-mono">
          <span className="text-text-3">
            Page <strong className="text-text-1">{currentPage}</strong> sur <strong className="text-text-1">{totalPages}</strong> ({total} éléments)
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onPageChange(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="p-1.5 rounded-lg border border-border-strong/30 bg-surface-2 hover:bg-surface-hover text-text-1 disabled:opacity-40 transition-colors cursor-pointer"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <button
              onClick={() => onPageChange(offset + limit)}
              disabled={currentPage >= totalPages}
              className="p-1.5 rounded-lg border border-border-strong/30 bg-surface-2 hover:bg-surface-hover text-text-1 disabled:opacity-40 transition-colors cursor-pointer"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
