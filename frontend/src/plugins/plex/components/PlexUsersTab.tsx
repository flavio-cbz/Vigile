import React from 'react';
import { Clock, Radio } from 'lucide-react';

export interface PlexUser {
  id?: string;
  name: string;
  default_subtitle_language?: string;
  last_seen_at?: number | null;
  is_online?: boolean;
}

interface PlexUsersTabProps {
  users: PlexUser[];
}

function formatLastSeen(timestamp?: number | null): string {
  if (!timestamp) return 'Aucune activité récente';
  const now = Math.floor(Date.now() / 1000);
  const diff = now - timestamp;

  if (diff < 60) return "À l'instant";
  if (diff < 3600) return `Il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) {
    const hours = Math.floor(diff / 3600);
    return `Il y a ${hours} ${hours > 1 ? 'heures' : 'heure'}`;
  }
  if (diff < 172800) {
    const d = new Date(timestamp * 1000);
    return `Hier à ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }
  const date = new Date(timestamp * 1000);
  return date.toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
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
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {users.map((u, i) => (
        <div
          key={u.id || i}
          className="flex items-center gap-3.5 p-3.5 bg-surface-2/40 border border-border-strong/15 rounded-xl hover:bg-surface-2/60 transition-colors"
        >
          <div className="relative shrink-0">
            <div className="w-9 h-9 rounded-full bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-xs font-bold text-orange-500">
              {u.name ? u.name.substring(0, 2).toUpperCase() : 'US'}
            </div>
            {u.is_online && (
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-surface shadow-[0_0_6px_rgba(16,185,129,0.5)]" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-bold text-text-1 truncate">{u.name || 'Utilisateur Plex'}</div>
            <div className="text-[11px] font-mono mt-0.5 flex items-center gap-1.5">
              {u.is_online ? (
                <span className="text-emerald-400 font-semibold flex items-center gap-1">
                  <Radio className="w-3 h-3 animate-pulse" />
                  En ligne (lecture active)
                </span>
              ) : u.last_seen_at ? (
                <span className="text-text-3 flex items-center gap-1 truncate">
                  <Clock className="w-3 h-3 text-orange-400 shrink-0" />
                  Dernière connexion : <strong className="text-text-2">{formatLastSeen(u.last_seen_at)}</strong>
                </span>
              ) : (
                <span className="text-text-3/60 italic">Aucune activité enregistrée</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
