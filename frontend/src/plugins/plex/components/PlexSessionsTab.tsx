import React from 'react';
import { Play, Pause, User, Tv, Zap, XCircle } from 'lucide-react';

export interface PlexSession {
  session_key?: string;
  title: string;
  grandparent_title?: string;
  parent_title?: string;
  user: string;
  user_thumb?: string;
  player_device?: string;
  player_platform?: string;
  state: 'playing' | 'paused' | 'buffering';
  progress_percent?: number;
  quality_profile?: string;
  bandwidth_kbps?: number;
  transcode: boolean;
  video_decision?: string;
  speed?: number;
  thumb?: string;
}

interface PlexSessionsTabProps {
  sessions: PlexSession[];
  nodeId?: string;
  onKillSession?: (sessionKey: string) => void;
  isAdmin?: boolean;
}

export const PlexSessionsTab: React.FC<PlexSessionsTabProps> = ({
  sessions,
  nodeId,
  onKillSession,
  isAdmin = false,
}) => {
  if (sessions.length === 0) {
    return (
      <div className="text-center py-12 text-text-3 text-xs uppercase tracking-wider font-mono bg-surface-1/30 rounded-xl border border-border-strong/10">
        Aucune session de lecture en cours
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {sessions.map((session, i) => {
        const progress = Math.min(Math.max(session.progress_percent || 0, 0), 100);
        const posterUrl = session.thumb && nodeId
          ? `/api/plugins/plex/${nodeId}/photo?path=${encodeURIComponent(session.thumb)}`
          : null;

        return (
          <div
            key={session.session_key || i}
            className="flex flex-col p-4 bg-surface-2/40 border border-border-strong/15 rounded-xl hover:bg-surface-2/60 transition-all gap-3"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex items-center gap-3.5">
                {posterUrl ? (
                  <img
                    src={posterUrl}
                    alt={session.title}
                    className="w-12 h-16 rounded-lg object-cover bg-surface-1 shrink-0 border border-border-strong/20"
                  />
                ) : (
                  <div className="w-12 h-12 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-500 shrink-0 border border-amber-500/20">
                    {session.state === 'playing' ? (
                      <Play className="w-5 h-5 fill-amber-500" />
                    ) : (
                      <Pause className="w-5 h-5" />
                    )}
                  </div>
                )}

                <div className="min-w-0">
                  <div className="text-base font-bold text-text-1 truncate">
                    {session.grandparent_title ? `${session.grandparent_title} - ` : ''}
                    {session.title}
                  </div>

                  <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-text-3">
                    <span className="flex items-center gap-1 font-medium text-text-2">
                      <User className="w-3.5 h-3.5 text-amber-500" /> {session.user}
                    </span>
                    <span className="flex items-center gap-1">
                      <Tv className="w-3.5 h-3.5 text-zinc-400" /> {session.player_device || 'Appareil inconnu'}
                      {session.player_platform && ` (${session.player_platform})`}
                    </span>
                    {session.bandwidth_kbps ? (
                      <span className="flex items-center gap-1 text-amber-500/90 font-mono">
                        <Zap className="w-3 h-3" /> {(session.bandwidth_kbps / 1000).toFixed(1)} Mbps
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="shrink-0 flex items-center gap-2">
                <span
                  className={`text-xs font-mono font-semibold px-2.5 py-1 rounded-md border ${
                    session.transcode
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/25'
                      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
                  }`}
                >
                  {session.transcode ? `Transcode ${session.speed ? `(${session.speed.toFixed(1)}x)` : ''}` : 'Direct Play'}
                </span>

                {isAdmin && session.session_key && onKillSession && (
                  <button
                    onClick={() => onKillSession(session.session_key!)}
                    title="Terminer la session"
                    className="p-1.5 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 rounded-lg transition-colors border border-rose-500/20"
                  >
                    <XCircle className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>

            {/* Progress bar */}
            <div className="w-full flex items-center gap-3">
              <div className="flex-1 h-2 bg-surface-1 rounded-full overflow-hidden border border-border-strong/10">
                <div
                  className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="text-[11px] font-mono text-text-3 font-semibold w-10 text-right">
                {Math.round(progress)}%
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

