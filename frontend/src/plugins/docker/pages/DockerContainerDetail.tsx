import React from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { Terminal, Info } from 'lucide-react';
import { PageHeader } from '../../../components/blocks/PageHeader';

interface DockerContainerDetailProps {
  api: PluginAPI;
  routeParams: Record<string, string | undefined>;
}

export const DockerContainerDetail: React.FC<DockerContainerDetailProps> = ({ api, routeParams }) => {
  const containerId = routeParams.containerId || 'unknown';

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      <PageHeader
        back={{ label: 'Retour aux conteneurs', onClick: () => api.navigate('/containers') }}
        title={`🐳 Conteneur ${containerId.slice(0, 12)}`}
        subtitle="Inspection détaillée et logs en streaming."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1 p-5 rounded-xl border border-border-strong/30 bg-surface-2/40 backdrop-blur-xs flex flex-col gap-4">
          <h3 className="text-sm font-bold uppercase font-mono text-text-3 flex items-center gap-2">
            <Info className="w-4 h-4 text-text-3" />
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

        <div className="md:col-span-2 p-5 rounded-xl border border-border-strong/30 bg-surface-2 flex flex-col gap-3 min-h-[300px]">
          <h3 className="text-sm font-bold uppercase font-mono text-text-2 flex items-center gap-2 border-b border-border-strong pb-2">
            <Terminal className="w-4 h-4 text-text-3 animate-pulse" />
            Logs de sortie
          </h3>
          <div className="flex-1 font-mono text-xs text-text-2 overflow-y-auto max-h-[400px] flex flex-col gap-1 select-text">
            <span className="text-text-3">[2026-07-14 10:52:11] Starting server...</span>
            <span className="text-green-custom/80">[2026-07-14 10:52:12] Database connection established successfully.</span>
            <span className="text-text-3">[2026-07-14 10:52:15] Server listening on port 8080.</span>
            <span className="text-text-3">[2026-07-14 10:54:02] GET /health - 200 OK</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DockerContainerDetail;
