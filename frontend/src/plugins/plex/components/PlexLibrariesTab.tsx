import React from 'react';
import { Film } from 'lucide-react';

export interface PlexLibrary {
  title: string;
  type: string;
}

interface PlexLibrariesTabProps {
  libraries: PlexLibrary[];
}

export const PlexLibrariesTab: React.FC<PlexLibrariesTabProps> = ({ libraries }) => {
  if (libraries.length === 0) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="col-span-2 text-center py-10 text-text-3 text-xs uppercase tracking-wider font-mono">
          Aucune bibliothèque détectée
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {libraries.map((lib, i) => (
        <div
          key={i}
          className="p-3.5 bg-surface-2/40 border border-border-strong/15 rounded-xl flex items-center gap-3"
        >
          <Film className="w-5 h-5 text-orange-500 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-bold text-text-1 truncate">{lib.title}</div>
            <div className="text-[10px] text-text-3 uppercase font-semibold mt-0.5">
              {lib.type}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
