import React from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { ArrowLeft, Terminal, Info } from 'lucide-react';

interface DockerContainerDetailProps {
  api: PluginAPI;
  routeParams: Record<string, string | undefined>;
}

export const DockerContainerDetail: React.FC<DockerContainerDetailProps> = ({ api, routeParams }) => {
  const containerId = routeParams.containerId || 'unknown';

  return (
    <div className="p-6 max-w-4xl mx-auto flex flex-col gap-6 animate-fade-in">
      <div>
        <button
          onClick={() => api.navigate('/containers')}
          className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-text-3 hover:text-text-1 mb-4 transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Retour aux conteneurs
        </button>

        <h1 className="text-2xl font-bold text-text-1 flex items-center gap-2">
          🐳 Conteneur {containerId.slice(0, 12)}
        </h1>
        <p className="text-sm text-text-3 mt-1">
          Inspection détaillée et logs en streaming.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1 p-5 rounded-xl border border-border-strong/30 bg-surface-2/40 backdrop-blur-xs flex flex-col gap-4">
          <h3 className="text-sm font-bold uppercase font-mono text-text-3 flex items-center gap-2">
            <Info className="w-4 h-4 text-zinc-500" />
            Métadonnées
          </h3>
          <div className="flex flex-col gap-2 font-mono text-xs">
            <div>
              <span className="text-text-3">ID:</span>
              <span className="text-text-1 ml-2 select-all">{containerId}</span>
            </div>
            <div>
              <span className="text-text-3">Status:</span>
              <span className="text-green-custom ml-2 font-semibold">Running</span>
            </div>
          </div>
        </div>

        <div className="md:col-span-2 p-5 rounded-xl border border-border-strong/30 bg-zinc-950 flex flex-col gap-3 min-h-[300px]">
          <h3 className="text-sm font-bold uppercase font-mono text-zinc-400 flex items-center gap-2 border-b border-zinc-800 pb-2">
            <Terminal className="w-4 h-4 text-zinc-500 animate-pulse" />
            Logs de sortie
          </h3>
          <div className="flex-1 font-mono text-xs text-zinc-400 overflow-y-auto max-h-[400px] flex flex-col gap-1 select-text">
            <span className="text-zinc-600">[2026-07-14 10:52:11] Starting server...</span>
            <span className="text-green-custom/80">[2026-07-14 10:52:12] Database connection established successfully.</span>
            <span className="text-zinc-500">[2026-07-14 10:52:15] Server listening on port 8080.</span>
            <span className="text-zinc-500">[2026-07-14 10:54:02] GET /health - 200 OK</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DockerContainerDetail;
