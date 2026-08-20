import React, { useState } from 'react';
import { Folder, HardDrive, RefreshCw, Film, FileText, Search } from 'lucide-react';

export interface PlexLibraryFileSummary {
  key: string;
  title: string;
  type: string;
  locations: string[];
  total_files: number;
  total_size_bytes: number;
}

export interface PlexMediaFile {
  section: string;
  section_type: string;
  title: string;
  file_path: string;
  size_bytes: number;
  container?: string;
  resolution?: string;
  codec?: string;
  added_at?: number;
}

interface PlexFilesTabProps {
  libraries: PlexLibraryFileSummary[];
  largestFiles: PlexMediaFile[];
  totalStorageBytes: number;
  nodeId: string;
  onScanLibrary?: (sectionId: string) => void;
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'Ko', 'Mo', 'Go', 'To'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = (bytes / Math.pow(k, i)).toFixed(1);
  return `${val} ${sizes[i]}`;
}

export const PlexFilesTab: React.FC<PlexFilesTabProps> = ({
  libraries,
  largestFiles,
  totalStorageBytes,
  onScanLibrary,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [scanningKey, setScanningKey] = useState<string | null>(null);

  const filteredFiles = largestFiles.filter(
    (f) =>
      f.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.file_path.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.section.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleScan = async (sectionKey: string) => {
    setScanningKey(sectionKey);
    try {
      if (onScanLibrary) await onScanLibrary(sectionKey);
    } finally {
      setScanningKey(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Storage Overview Header */}
      <div className="p-4 bg-surface-2/40 border border-border-strong/15 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-400 shrink-0">
            <HardDrive className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-1 font-mono">Emplacements Médias & Analyse Stockage</h3>
            <p className="text-xs text-text-3 font-mono mt-0.5">
              Taille estimée des bibliothèques : <strong className="text-orange-400">{formatBytes(totalStorageBytes)}</strong>
            </p>
          </div>
        </div>
      </div>

      {/* Library Locations Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {libraries.map((lib) => (
          <div
            key={lib.key}
            className="p-4 bg-surface-2/30 border border-border-strong/15 rounded-xl flex flex-col justify-between gap-3 hover:bg-surface-2/50 transition-all"
          >
            <div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Film className="w-4 h-4 text-orange-500" />
                  <span className="text-sm font-bold text-text-1">{lib.title}</span>
                </div>
                <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-surface-3 text-text-3">
                  {lib.type}
                </span>
              </div>

              <div className="mt-3 flex flex-col gap-1 text-xs font-mono text-text-3">
                <div className="flex items-center justify-between">
                  <span>Fichiers totaux :</span>
                  <strong className="text-text-1">{lib.total_files}</strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Espace estimé :</span>
                  <strong className="text-text-1">{formatBytes(lib.total_size_bytes)}</strong>
                </div>
              </div>

              {lib.locations.length > 0 && (
                <div className="mt-2.5 pt-2.5 border-t border-border-strong/10 flex flex-col gap-1">
                  <span className="text-[10px] font-mono uppercase text-text-3 font-bold flex items-center gap-1">
                    <Folder className="w-3 h-3 text-amber-500" /> Dossier(s) source :
                  </span>
                  {lib.locations.map((loc, i) => (
                    <code key={i} className="text-[11px] font-mono text-text-2 bg-surface-3/60 px-2 py-1 rounded truncate">
                      {loc}
                    </code>
                  ))}
                </div>
              )}
            </div>

            {onScanLibrary && (
              <button
                onClick={() => handleScan(lib.key)}
                disabled={scanningKey === lib.key}
                className="mt-2 w-full py-1.5 px-3 rounded-lg border border-border-strong/30 bg-surface-3/40 hover:bg-surface-hover text-text-1 text-xs font-mono font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${scanningKey === lib.key ? 'animate-spin text-orange-400' : ''}`} />
                Scan Bibliothèque
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Media Files Table (Largest Files) */}
      <div className="p-4 bg-surface-2/30 border border-border-strong/15 rounded-xl flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-orange-500" />
            <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-text-1">
              Fichiers Volumineux Récents ({filteredFiles.length})
            </h4>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 text-text-3 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filtrer par titre ou chemin..."
              className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-border-strong/30 bg-surface-3/50 text-text-1 font-mono focus:outline-none focus:border-orange-500/50"
            />
          </div>
        </div>

        {filteredFiles.length === 0 ? (
          <div className="text-center py-8 text-text-3 text-xs uppercase font-mono">
            Aucun fichier trouvé
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs font-mono">
              <thead>
                <tr className="border-b border-border-strong/20 text-text-3 text-[11px] uppercase">
                  <th className="py-2 px-3 font-semibold">Titre / Média</th>
                  <th className="py-2 px-3 font-semibold">Section</th>
                  <th className="py-2 px-3 font-semibold">Format / Résolution</th>
                  <th className="py-2 px-3 font-semibold text-right">Taille sur disque</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-strong/10">
                {filteredFiles.map((file, idx) => (
                  <tr key={idx} className="hover:bg-surface-2/60 transition-colors">
                    <td className="py-2.5 px-3">
                      <div className="font-bold text-text-1 text-sm">{file.title}</div>
                      <div className="text-[11px] text-text-3 truncate max-w-md mt-0.5">
                        {file.file_path}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-text-2">{file.section}</td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5">
                        {file.resolution && (
                          <span className="px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-400 border border-orange-500/20 text-[10px] font-bold uppercase">
                            {file.resolution}
                          </span>
                        )}
                        {file.container && (
                          <span className="px-1.5 py-0.5 rounded bg-surface-3 text-text-3 text-[10px] uppercase">
                            .{file.container}
                          </span>
                        )}
                        {file.codec && <span className="text-text-3 text-[10px]">({file.codec})</span>}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold text-text-1">
                      {formatBytes(file.size_bytes)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
