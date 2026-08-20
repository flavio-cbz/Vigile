import React from 'react';
import { Zap, Download, Cpu, ArrowRight } from 'lucide-react';

export interface PlexTranscodeItem {
  session_key: string;
  title: string;
  grandparent_title?: string;
  user: string;
  device: string;
  video_decision: string;
  audio_decision: string;
  video_codec?: string;
  audio_codec?: string;
  speed: number;
  progress: number;
  throttled: boolean;
  bandwidth_kbps: number;
  context: string;
}

export interface PlexDownloadItem {
  id: string;
  title: string;
  user: string;
  state: string;
  progress: number;
  size_bytes: number;
  device_name: string;
}

interface PlexTranscodesTabProps {
  transcodes: PlexTranscodeItem[];
  downloads: PlexDownloadItem[];
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'Ko', 'Mo', 'Go', 'To'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = (bytes / Math.pow(k, i)).toFixed(1);
  return `${val} ${sizes[i]}`;
}

export const PlexTranscodesTab: React.FC<PlexTranscodesTabProps> = ({ transcodes, downloads }) => {
  const hasItems = transcodes.length > 0 || downloads.length > 0;

  if (!hasItems) {
    return (
      <div className="text-center py-12 text-text-3 text-xs uppercase tracking-wider font-mono bg-surface-1/30 rounded-xl border border-border-strong/10">
        Aucun transcodage ou téléchargement actif
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Transcodes Section */}
      {transcodes.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-text-2 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" /> Transcodages en direct ({transcodes.length})
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3">
            {transcodes.map((item) => (
              <div
                key={item.session_key}
                className="p-4 bg-surface-2/40 border border-border-strong/15 rounded-xl flex flex-col gap-3 hover:bg-surface-2/60 transition-all"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-bold text-text-1 flex items-center gap-2">
                      {item.grandparent_title ? `${item.grandparent_title} - ` : ''}
                      {item.title}
                    </div>
                    <div className="text-xs text-text-3 font-mono mt-1 flex flex-wrap items-center gap-3">
                      <span>Utilisateur : <strong className="text-text-2">{item.user}</strong></span>
                      <span>•</span>
                      <span>Appareil : <strong className="text-text-2">{item.device}</strong></span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs font-mono font-bold px-2.5 py-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/25 flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5" /> {item.speed ? `${item.speed.toFixed(1)}x` : '1.0x'}
                    </span>
                    {item.throttled && (
                      <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
                        Throttled (Économie)
                      </span>
                    )}
                  </div>
                </div>

                {/* Technical Conversion details */}
                <div className="p-3 bg-surface-3/50 rounded-lg border border-border-strong/20 flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
                  <div className="flex items-center gap-2">
                    <span className="text-text-3">Vidéo :</span>
                    <span className="text-amber-400 font-semibold uppercase">{item.video_decision}</span>
                    {item.video_codec && <span className="text-text-3">({item.video_codec})</span>}
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-text-3 hidden sm:block" />
                  <div className="flex items-center gap-2">
                    <span className="text-text-3">Audio :</span>
                    <span className="text-amber-400 font-semibold uppercase">{item.audio_decision}</span>
                    {item.audio_codec && <span className="text-text-3">({item.audio_codec})</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-text-3">Débit :</span>
                    <span className="text-text-1 font-bold">{(item.bandwidth_kbps / 1000).toFixed(1)} Mbps</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Downloads / Sync Section */}
      {downloads.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-text-2 flex items-center gap-2">
              <Download className="w-4 h-4 text-blue-400" /> Téléchargements & Synchronisations ({downloads.length})
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3">
            {downloads.map((item) => (
              <div
                key={item.id}
                className="p-4 bg-surface-2/40 border border-border-strong/15 rounded-xl flex flex-col gap-3 hover:bg-surface-2/60 transition-all"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-bold text-text-1">{item.title}</div>
                    <div className="text-xs text-text-3 font-mono mt-1 flex items-center gap-3">
                      <span>Utilisateur : <strong className="text-text-2">{item.user}</strong></span>
                      <span>•</span>
                      <span>Appareil : <strong className="text-text-2">{item.device_name}</strong></span>
                      {item.size_bytes > 0 && (
                        <>
                          <span>•</span>
                          <span>Taille : <strong className="text-text-2">{formatBytes(item.size_bytes)}</strong></span>
                        </>
                      )}
                    </div>
                  </div>

                  <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/25 uppercase">
                    {item.state}
                  </span>
                </div>

                <div className="w-full flex items-center gap-3">
                  <div className="flex-1 h-2 bg-surface-1 rounded-full overflow-hidden border border-border-strong/10">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all duration-300"
                      style={{ width: `${Math.min(Math.max(item.progress, 0), 100)}%` }}
                    />
                  </div>
                  <span className="text-[11px] font-mono text-text-3 font-semibold w-10 text-right">
                    {Math.round(item.progress)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
