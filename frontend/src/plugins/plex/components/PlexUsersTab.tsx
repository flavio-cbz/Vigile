import React from 'react';

export interface PlexUser {
  name: string;
  default_subtitle_language?: string;
}

interface PlexUsersTabProps {
  users: PlexUser[];
}

export const PlexUsersTab: React.FC<PlexUsersTabProps> = ({ users }) => {
  if (users.length === 0) {
    return (
      <div className="text-center py-10 text-text-3 text-xs uppercase tracking-wider font-mono">
        Aucun utilisateur Plex trouvé
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {users.map((u, i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-3.5 bg-surface-2/40 border border-border-strong/15 rounded-xl"
        >
          <div className="w-8 h-8 rounded-full bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-xs font-bold text-orange-500">
            {u.name ? u.name.substring(0, 2).toUpperCase() : 'US'}
          </div>
          <div>
            <div className="text-sm font-bold text-text-1">{u.name || 'Utilisateur Plex'}</div>
            {u.default_subtitle_language && (
              <div className="text-[10px] text-text-3 mt-0.5">
                Langue des sous-titres : {u.default_subtitle_language}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
