import React, { useEffect, useState } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import { Play, Square, RotateCw, Server, Search, AlertCircle, RefreshCw, Activity } from 'lucide-react';

interface Service {
  node_id: string;
  name: string;
  state: string;
  status: string;
}

interface SystemdServicesProps {
  api: PluginAPI;
}

export const SystemdServices: React.FC<SystemdServicesProps> = ({ api }) => {
  const { nodes } = useNodeStore();
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedNode, setSelectedNode] = useState<string>('all');
  const [stateFilter, setStateFilter] = useState<string>('all');
  const [actionInProgress, setActionInProgress] = useState<Record<string, boolean>>({});

  const fetchServices = async () => {
    setLoading(true);
    try {
      const url = selectedNode === 'all' ? '/services' : `/services?node_id=${selectedNode}`;
      const data = await api.fetch<{ services: Service[] }>(url);
      setServices(data?.services || []);
    } catch (err) {
      console.error('Failed to fetch systemd services:', err);
      api.toast(
        err instanceof Error ? err.message : 'Erreur lors du chargement des services',
        'error'
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchServices();
  }, [selectedNode]);

  const handleServiceAction = async (nodeId: string, serviceName: string, action: string) => {
    const key = `${nodeId}-${serviceName}`;
    setActionInProgress((prev) => ({ ...prev, [key]: true }));
    try {
      // Dispatch systemd action via the API
      await api.fetch(`/services/${serviceName}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId }),
      });
      api.toast(`Action ${action} envoyée avec succès pour le service ${serviceName}`, 'success');
      setTimeout(fetchServices, 2000); // Refresh list
    } catch (err) {
      console.error(`Failed to trigger action ${action} on service ${serviceName}:`, err);
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

  const filteredServices = services.filter((s) => {
    const matchesSearch = s.name.toLowerCase().includes(searchTerm.toLowerCase());

    let matchesState = true;
    if (stateFilter === 'active') {
      matchesState = s.state.toLowerCase() === 'active';
    } else if (stateFilter === 'inactive') {
      matchesState = s.state.toLowerCase() === 'inactive';
    } else if (stateFilter === 'failed') {
      matchesState = s.state.toLowerCase() === 'failed' || s.status.toLowerCase() === 'failed';
    }

    return matchesSearch && matchesState;
  });

  return (
    <div className="p-6 max-w-7xl mx-auto flex flex-col gap-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-1 flex items-center gap-2">
            <Activity className="w-6 h-6 text-orange-500" />
            Services Systemd
          </h1>
          <p className="text-sm text-text-3 mt-1">
            Gérez et supervisez l'état des services et daemons système.
          </p>
        </div>

        <button
          onClick={fetchServices}
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
            placeholder="Rechercher par nom de service..."
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
            <span className="text-xs text-text-3 font-mono uppercase">État:</span>
            <select
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
            >
              <option value="all">Tous les états</option>
              <option value="active">Actifs (Active)</option>
              <option value="inactive">Inactifs (Inactive)</option>
              <option value="failed">Échoués (Failed)</option>
            </select>
          </div>
        </div>
      </div>

      {loading && services.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-2xl border border-zinc-800/40">
          <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4"></div>
          <span className="text-zinc-500 text-sm font-mono">Chargement des services...</span>
        </div>
      ) : filteredServices.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6">
          <AlertCircle className="w-12 h-12 text-zinc-600 mb-4" />
          <h3 className="text-lg font-bold text-zinc-300">Aucun service trouvé</h3>
          <p className="text-zinc-500 text-sm max-w-md mt-1">
            Aucun service systemd ne correspond aux critères de recherche actuels.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-border-strong/40 bg-surface-2/30 font-mono text-[10px] text-text-3 uppercase tracking-wider select-none">
                <th className="px-6 py-4 font-bold">Nom du service</th>
                <th className="px-6 py-4 font-bold">Serveur</th>
                <th className="px-6 py-4 font-bold">État active</th>
                <th className="px-6 py-4 font-bold">Statut sub</th>
                <th className="px-6 py-4 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredServices.map((s) => {
                const key = `${s.node_id}-${s.name}`;
                const inProgress = actionInProgress[key];
                const isActive = s.state.toLowerCase() === 'active';

                return (
                  <tr
                    key={key}
                    className="border-b border-border-strong/15 hover:bg-surface-2/20 transition-colors duration-150 text-sm"
                  >
                    <td className="px-6 py-4 font-semibold text-text-1 font-mono text-xs">
                      {s.name}
                    </td>
                    <td className="px-6 py-4 text-text-2 font-mono text-xs">
                      <span className="flex items-center gap-1.5 text-zinc-400">
                        <Server className="w-3.5 h-3.5 text-zinc-500" />
                        {getNodeName(s.node_id)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold leading-none ${
                          isActive
                            ? 'bg-green-custom/10 text-green-custom border border-green-custom/20'
                            : 'bg-zinc-800 text-zinc-400 border border-zinc-700/50'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            isActive ? 'bg-green-custom animate-pulse' : 'bg-zinc-500'
                          }`}
                        />
                        {s.state}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-text-3">
                      {s.status}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        {isActive ? (
                          <button
                            onClick={() => handleServiceAction(s.node_id, s.name, 'stop')}
                            disabled={inProgress}
                            className="p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors border border-transparent hover:border-zinc-700/50 cursor-pointer"
                            title="Arrêter le service"
                          >
                            <Square className="w-4 h-4" />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleServiceAction(s.node_id, s.name, 'start')}
                            disabled={inProgress}
                            className="p-1.5 rounded hover:bg-green-custom/10 text-green-custom hover:text-green-custom transition-colors border border-transparent hover:border-green-custom/20 cursor-pointer"
                            title="Démarrer le service"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => handleServiceAction(s.node_id, s.name, 'restart')}
                          disabled={inProgress}
                          className="p-1.5 rounded hover:bg-orange-500/10 text-orange-500 hover:text-orange-400 transition-colors border border-transparent hover:border-orange-500/20 cursor-pointer"
                          title="Redémarrer le service"
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

export default SystemdServices;
