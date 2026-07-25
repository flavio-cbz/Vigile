import React from 'react';
import { Play, Pause, User, Tv } from 'lucide-react';

export interface PlexSession {
  title: string;
  grandparent_title?: string;
  user: string;
  device?: string;
  state: 'playing' | 'paused';
  transcode: boolean;
}

interface PlexSessionsTabProps {
  sessions: PlexSession[];
}

export const PlexSessionsTab: React.FC<PlexSessionsTabProps> = ({ sessions }) => {
  if (sessions.length === 0) {
    return (
      <div className="text-center py-10 text-text-3 text-xs uppercase tracking-wider font-mono">
        Aucune session de lecture en cours
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {sessions.map((session, i) => (
        <div
          key={i}
          className="flex items-center justify-between p-3.5 bg-surface-2/40 border border-border-strong/15 rounded-xl hover:bg-surface-2/70 transition-colors"
        >
          <div className="min-w-0 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-orange-500/10 flex items-center justify-center text-orange-500 shrink-0 border border-orange-500/20">
              {session.state === 'playing' ? (
                <Play className="w-4 h-4 fill-orange-500" />
              ) : (
                <Pause className="w-4 h-4" />
              )}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-bold text-text-1 truncate">
                {session.grandparent_title ? `${session.grandparent_title} - ` : ''}
                {session.title}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-text-3">
                <span className="flex items-center gap-1">
                  <User className="w-3.5 h-3.5 text-zinc-500" /> {session.user}
                </span>
                <span className="flex items-center gap-1 truncate">
                  <Tv className="w-3.5 h-3.5 text-zinc-500" /> {session.device || 'Inconnu'}
                </span>
              </div>
            </div>
          </div>
          <div className="shrink-0 flex items-center gap-1.5 ml-4">
            <span
              className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${
                session.transcode
                  ? 'bg-orange-500/10 text-orange-500 border-orange-500/20'
                  : 'bg-green-custom/10 text-green-custom border-green-custom/20'
              }`}
            >
              {session.transcode ? 'Transcode' : 'Direct Play'}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
};
