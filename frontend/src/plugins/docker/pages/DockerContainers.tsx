import React, { useEffect, useState } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { Play, Square, RotateCw, Server, Search, AlertCircle, RefreshCw } from 'lucide-react';

interface Container {
  node_id: string;
  id: string;
  name: string;
  image: string;
  state: string;
  ports: string[];
}

interface DockerContainersProps {
  api: PluginAPI;
}

export const DockerContainers: React.FC<DockerContainersProps> = ({ api }) => {
  const { nodes } = useNodeStore();
  const [containers, setContainers] = useState<Container[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedNode, setSelectedNode] = useState<string>('all');
  const [stateFilter, setStateFilter] = useState<string>('all');
  const [actionInProgress, setActionInProgress] = useState<Record<string, boolean>>({});

  const fetchContainers = async () => {
    setLoading(true);
    try {
      const url = selectedNode === 'all' ? '/containers' : `/containers?node_id=${selectedNode}`;
      const data = await api.fetch<{ containers: Container[] }>(url);
      setContainers(data?.containers || []);
    } catch (err) {
      console.error('Failed to fetch docker containers:', err);
      api.toast(
        err instanceof Error ? err.message : 'Erreur lors du chargement des conteneurs',
        'error'
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContainers();
  }, [selectedNode]);

  const handleContainerAction = async (nodeId: string, containerId: string, action: string) => {
    const key = `${nodeId}-${containerId}`;
    setActionInProgress((prev) => ({ ...prev, [key]: true }));
    try {
      // Vigile orchestrates container actions via nodes REST API (as approved in design)
      await api.fetch(`/containers/${containerId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId }),
      });
      api.toast(`Action ${action} envoyée avec succès pour le conteneur ${containerId}`, 'success');
      setTimeout(fetchContainers, 2000); // Reload after delay to let the state transition
    } catch (err) {
      console.error(`Failed to trigger action ${action} on container ${containerId}:`, err);
      api.toast(
        err instanceof Error ? err.message : `L'action ${action} a échoué`,
        'error'
      );
    } finally {
      setActionInProgress((prev) => ({ ...prev, [key]: false }));
    }
  };

  const getNodeName = (nodeId: string) => {
    const n = nodes.find((node) => node.id === nodeId);
    return n ? n.name : nodeId.slice(0, 8);
  };

  const filteredContainers = containers.filter((c) => {
    // 1. Search term
    const matchesSearch =
      c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.image.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.id.toLowerCase().includes(searchTerm.toLowerCase());

    // 2. State filter
    let matchesState = true;
    if (stateFilter === 'running') {
      matchesState = c.state.toLowerCase() === 'running';
    } else if (stateFilter === 'stopped') {
      matchesState = c.state.toLowerCase() === 'exited' || c.state.toLowerCase() === 'created';
    } else if (stateFilter === 'failed') {
      matchesState =
        c.state.toLowerCase() === 'dead' ||
        (c.state.toLowerCase() === 'exited' && c.name.includes('fail')); // Simplification for failed state check
    }

    return matchesSearch && matchesState;
  });

  return (
    <div className="p-6 max-w-7xl mx-auto flex flex-col gap-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-1 flex items-center gap-2">
            🐳 Conteneurs Docker
          </h1>
          <p className="text-sm text-text-3 mt-1">
            Gérez et supervisez les conteneurs Docker en temps réel sur l'ensemble de votre flotte.
          </p>
        </div>

        <button
          onClick={fetchContainers}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Rafraîchir
        </button>
      </div>

      {/* Filter panel */}
      <div className="flex flex-col md:flex-row gap-4 p-4 rounded-xl bg-surface-2/40 border border-border-strong/30 backdrop-blur-xs">
        <div className="flex-1 relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-3" />
          <input
            type="text"
            placeholder="Rechercher par nom, image ou ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all duration-150"
          />
        </div>

        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-3 font-mono uppercase">Serveur:</span>
            <select
              value={selectedNode}
              onChange={(e) => setSelectedNode(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
            >
              <option value="all">Tous les serveurs</option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-text-3 font-mono uppercase">Statut:</span>
            <select
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
            >
              <option value="all">Tous les statuts</option>
              <option value="running">En cours d'exécution</option>
              <option value="stopped">Arrêtés</option>
              <option value="failed">Échoués</option>
            </select>
          </div>
        </div>
      </div>

      {loading && containers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-2xl border border-zinc-800/40">
          <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4"></div>
          <span className="text-zinc-500 text-sm font-mono">Chargement des conteneurs...</span>
        </div>
      ) : filteredContainers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6">
          <AlertCircle className="w-12 h-12 text-zinc-600 mb-4" />
          <h3 className="text-lg font-bold text-zinc-300">Aucun conteneur trouvé</h3>
          <p className="text-zinc-500 text-sm max-w-md mt-1">
            Aucun conteneur Docker ne correspond aux critères de recherche actuels.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-border-strong/40 bg-surface-2/30 font-mono text-[10px] text-text-3 uppercase tracking-wider select-none">
                <th className="px-6 py-4 font-bold">Conteneur</th>
                <th className="px-6 py-4 font-bold">Image</th>
                <th className="px-6 py-4 font-bold">Serveur</th>
                <th className="px-6 py-4 font-bold">Ports</th>
                <th className="px-6 py-4 font-bold">Statut</th>
                <th className="px-6 py-4 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredContainers.map((c) => {
                const key = `${c.node_id}-${c.id}`;
                const inProgress = actionInProgress[key];
                const isRunning = c.state.toLowerCase() === 'running';

                return (
                  <tr
                    key={key}
                    className="border-b border-border-strong/15 hover:bg-surface-2/20 transition-colors duration-150 text-sm"
                  >
                    <td className="px-6 py-4 font-semibold text-text-1">
                      <div className="flex flex-col">
                        <span>{c.name}</span>
                        <span className="text-[10px] text-text-3 font-mono mt-0.5">{c.id.slice(0, 12)}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-text-2 font-mono text-xs max-w-[200px] truncate" title={c.image}>
                      {c.image}
                    </td>
                    <td className="px-6 py-4 text-text-2 font-mono text-xs">
                      <span className="flex items-center gap-1.5 text-zinc-400">
                        <Server className="w-3.5 h-3.5 text-zinc-500" />
                        {getNodeName(c.node_id)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      {c.ports && c.ports.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {c.ports.slice(0, 3).map((p, idx) => (
                            <span
                              key={idx}
                              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/40"
                            >
                              {p}
                            </span>
                          ))}
                          {c.ports.length > 3 && (
                            <span className="text-[9px] font-mono text-zinc-500 px-1">
                              +{c.ports.length - 3}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-text-3 font-mono">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold leading-none ${
                          isRunning
                            ? 'bg-green-custom/10 text-green-custom border border-green-custom/20'
                            : 'bg-zinc-800 text-zinc-400 border border-zinc-700/50'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            isRunning ? 'bg-green-custom animate-pulse' : 'bg-zinc-500'
                          }`}
                        />
                        {c.state}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        {isRunning ? (
                          <button
                            onClick={() => handleContainerAction(c.node_id, c.id, 'stop')}
                            disabled={inProgress}
                            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors border border-transparent hover:border-zinc-700/50 cursor-pointer"
                            title="Arrêter le conteneur"
                          >
                            <Square className="w-4 h-4" />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleContainerAction(c.node_id, c.id, 'start')}
                            disabled={inProgress}
                            className="p-1.5 rounded hover:bg-green-custom/10 text-green-custom hover:text-green-custom transition-colors border border-transparent hover:border-green-custom/20 cursor-pointer"
                            title="Démarrer le conteneur"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => handleContainerAction(c.node_id, c.id, 'restart')}
                          disabled={inProgress}
                          className="p-1.5 rounded hover:bg-orange-500/10 text-orange-500 hover:text-orange-400 transition-colors border border-transparent hover:border-orange-500/20 cursor-pointer"
                          title="Redémarrer le conteneur"
                        >
                          <RotateCw className={`w-4 h-4 ${inProgress ? 'animate-spin' : ''}`} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default DockerContainers;
