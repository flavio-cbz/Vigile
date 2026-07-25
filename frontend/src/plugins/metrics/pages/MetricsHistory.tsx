import React, { useEffect, useState } from 'react';
import type { PluginAPI } from '../../../types/plugins';
import { useNodeStore } from '../../../store/nodeStore';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from 'recharts';
import { Server, Activity, RefreshCw, AlertCircle, Clock } from 'lucide-react';

interface MetricPoint {
  node_id: string;
  collected_at: number;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
}

interface MetricsHistoryProps {
  api: PluginAPI;
}

export const MetricsHistory: React.FC<MetricsHistoryProps> = ({ api }) => {
  const { nodes } = useNodeStore();
  const [history, setHistory] = useState<MetricPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string>('all');
  const [period, setPeriod] = useState<string>('24h');

  const fetchHistory = async () => {
    setLoading(true);
    try {
      let url = `/history?period=${period}`;
      if (selectedNode !== 'all') {
        url += `&node_id=${selectedNode}`;
      }
      const data = await api.fetch<{ history: MetricPoint[] }>(url);
      setHistory(data?.history || []);
    } catch (err) {
      console.error('Failed to fetch metrics history:', err);
      api.toast(
        err instanceof Error ? err.message : 'Erreur lors du chargement de l\'historique',
        'error'
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [selectedNode, period]);

  // Format timestamp for display in Recharts X-axis
  const formatXAxis = (tickItem: number) => {
    const d = new Date(tickItem * 1000);
    if (period === '1h' || period === '6h') {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit' });
  };

  const formatTooltipDate = (label: unknown) => {
    return new Date(Number(label) * 1000).toLocaleString();
  };

  return (
    <div className="p-6 max-w-7xl mx-auto flex flex-col gap-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-1 flex items-center gap-2">
            <Activity className="w-6 h-6 text-accent" />
            Historique des Métriques
          </h1>
          <p className="text-sm text-text-3 mt-1">
            Supervisez les tendances d'utilisation des ressources système de votre flotte.
          </p>
        </div>

        <button
          onClick={fetchHistory}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Rafraîchir
        </button>
      </div>

      {/* Control panel */}
      <div className="flex flex-col md:flex-row gap-4 p-4 rounded-xl bg-surface-2/40 border border-border-strong/30 backdrop-blur-xs">
        <div className="flex flex-wrap gap-4 items-center flex-1">
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-text-3" />
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
            <Clock className="w-4 h-4 text-text-3" />
            <span className="text-xs text-text-3 font-mono uppercase">Période:</span>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
            >
              <option value="1h">Dernière heure</option>
              <option value="6h">Dernières 6 heures</option>
              <option value="24h">Dernières 24 heures</option>
              <option value="7d">Derniers 7 jours</option>
            </select>
          </div>
        </div>
      </div>

      {loading && history.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-2xl border border-zinc-800/40">
          <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4"></div>
          <span className="text-zinc-500 text-sm font-mono">Chargement de l'historique...</span>
        </div>
      ) : history.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6">
          <AlertCircle className="w-12 h-12 text-zinc-600 mb-4" />
          <h3 className="text-lg font-bold text-zinc-300">Aucune métrique enregistrée</h3>
          <p className="text-zinc-500 text-sm max-w-md mt-1">
            Aucun point de métrique n'est encore enregistré pour la période et le serveur sélectionnés.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* CPU Chart */}
          <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4">
            <h3 className="text-sm font-bold uppercase font-mono text-text-2 flex items-center gap-2">
              <Activity className="w-4 h-4 text-orange-500" />
              Utilisation du Processeur (CPU)
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="cpuColor" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f97316" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a/30" />
                  <XAxis dataKey="collected_at" tickFormatter={formatXAxis} stroke="#71717a" fontSize={10} />
                  <YAxis domain={[0, 100]} stroke="#71717a" fontSize={10} />
                  <Tooltip
                    labelFormatter={formatTooltipDate}
                    contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#f4f4f5' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="cpu_percent"
                    stroke="#f97316"
                    fillOpacity={1}
                    fill="url(#cpuColor)"
                    name="CPU (%)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Memory Chart */}
          <div className="p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4">
            <h3 className="text-sm font-bold uppercase font-mono text-text-2 flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-500" />
              Utilisation de la Mémoire RAM
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="memColor" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a/30" />
                  <XAxis dataKey="collected_at" tickFormatter={formatXAxis} stroke="#71717a" fontSize={10} />
                  <YAxis domain={[0, 100]} stroke="#71717a" fontSize={10} />
                  <Tooltip
                    labelFormatter={formatTooltipDate}
                    contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#f4f4f5' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="mem_percent"
                    stroke="#10b981"
                    fillOpacity={1}
                    fill="url(#memColor)"
                    name="RAM (%)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MetricsHistory;
