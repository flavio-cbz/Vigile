import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { useNodeStore, type Node } from '../store/nodeStore';
import { useAuthStore } from '../store/authStore';
import { useLocale } from '../i18n';
import { api } from '../hooks/useApi';
import { 
  Search, 
  ArrowUpDown, 
  Activity, 
  RefreshCw, 
  ChevronRight, 
  Terminal 
} from 'lucide-react';
import { usePolling } from '../hooks/usePolling';

interface MetricsMap {
  [nodeId: string]: {
    cpu: number;
    mem: number;
    disk: number;
    uptime: string;
    containersCount: number;
    loading: boolean;
  };
}

type SortField = 'name' | 'hostname' | 'online' | 'cpu' | 'mem' | 'disk' | 'containers' | 'uptime';
type SortOrder = 'asc' | 'desc';

export const Servers: React.FC = () => {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { nodes, fetchNodes, isLoading } = useNodeStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'online' | 'offline'>('all');
  const [nodeMetrics, setNodeMetrics] = useState<MetricsMap>({});
  const [sortField, setSortField] = useState<SortField>('name');
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');
  const [regeneratingMap, setRegeneratingMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetchNodes();
  }, [fetchNodes]);

  // Polling for nodes list updates
  usePolling('servers_list_page', () => {
    fetchNodes();
  }, 30000);

  // Fetch metrics in parallel for online nodes
  const fetchAllNodeDetails = async () => {
    const onlineNodes = nodes.filter((n) => n.online);
    if (onlineNodes.length === 0) return;

    setNodeMetrics((prev) => {
      const next = { ...prev };
      onlineNodes.forEach((node) => {
        if (!next[node.id]) {
          next[node.id] = { cpu: 0, mem: 0, disk: 0, uptime: 'N/A', containersCount: 0, loading: true };
        }
      });
      return next;
    });

    await Promise.all(
      onlineNodes.map(async (node) => {
        try {
          const statsPromise = api<any>(`/api/nodes/${node.id}/stats?limit=1`);
          const containersPromise = api<{ containers: any[] }>(`/api/nodes/${node.id}/containers`).catch(() => null);

          const [statsData, containersData] = await Promise.all([statsPromise, containersPromise]);

          let cpu = 0;
          let mem = 0;
          let disk = 0;
          let uptimeStr = 'N/A';
          let containersCount = 0;

          if (statsData && statsData.snapshots && statsData.snapshots.length > 0) {
            const snap = statsData.snapshots[0];
            cpu = Math.round(snap.cpu_percent);
            mem = Math.round(snap.mem_percent);
            disk = Math.round(snap.disk_percent);

            const uptSec = snap.uptime_seconds;
            const days = Math.floor(uptSec / 86400);
            const hrs = Math.floor((uptSec % 86400) / 3600);
            uptimeStr = days > 0 ? `${days}j ${hrs}h` : `${hrs}h`;
          }

          if (containersData && containersData.containers) {
            containersCount = containersData.containers.length;
          }

          setNodeMetrics((prev) => ({
            ...prev,
            [node.id]: { cpu, mem, disk, uptime: uptimeStr, containersCount, loading: false }
          }));
        } catch (e) {
          setNodeMetrics((prev) => ({
            ...prev,
            [node.id]: { cpu: 0, mem: 0, disk: 0, uptime: 'Error', containersCount: 0, loading: false }
          }));
        }
      })
    );
  };

  useEffect(() => {
    if (nodes.length > 0) {
      fetchAllNodeDetails();
    }
  }, [nodes]);

  const handleRegenerateProfile = async (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (regeneratingMap[nodeId]) return;

    setRegeneratingMap((prev) => ({ ...prev, [nodeId]: true }));
    try {
      await api(`/api/nodes/${nodeId}/profile/regenerate`, { method: 'POST' });
    } catch (err) {
      console.error(err);
    } finally {
      setRegeneratingMap((prev) => ({ ...prev, [nodeId]: false }));
    }
  };

  // Sorting and Filtering logic
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  const filteredNodes = nodes
    .filter((node) => {
      const matchesSearch =
        node.name.toLowerCase().includes(search.toLowerCase()) ||
        (node.hostname && node.hostname.toLowerCase().includes(search.toLowerCase())) ||
        (node.os && node.os.toLowerCase().includes(search.toLowerCase()));

      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'online' && node.online) ||
        (statusFilter === 'offline' && !node.online);

      return matchesSearch && matchesStatus;
    })
    .sort((a, b) => {
      let valA: any = a[sortField as keyof Node] ?? '';
      let valB: any = b[sortField as keyof Node] ?? '';

      // Overwrite for calculated metric values
      if (sortField === 'cpu') {
        valA = nodeMetrics[a.id]?.cpu ?? -1;
        valB = nodeMetrics[b.id]?.cpu ?? -1;
      } else if (sortField === 'mem') {
        valA = nodeMetrics[a.id]?.mem ?? -1;
        valB = nodeMetrics[b.id]?.mem ?? -1;
      } else if (sortField === 'disk') {
        valA = nodeMetrics[a.id]?.disk ?? -1;
        valB = nodeMetrics[b.id]?.disk ?? -1;
      } else if (sortField === 'containers') {
        valA = nodeMetrics[a.id]?.containersCount ?? -1;
        valB = nodeMetrics[b.id]?.containersCount ?? -1;
      } else if (sortField === 'uptime') {
        valA = nodeMetrics[a.id]?.uptime ?? '';
        valB = nodeMetrics[b.id]?.uptime ?? '';
      }

      if (typeof valA === 'string') {
        return sortOrder === 'asc'
          ? valA.localeCompare(valB)
          : valB.localeCompare(valA);
      } else {
        return sortOrder === 'asc' ? valA - valB : valB - valA;
      }
    });

  const getMetricColorClass = (percent: number) => {
    if (percent >= 90) return 'progress-bar-fill-danger';
    if (percent >= 75) return 'progress-bar-fill-warning';
    return 'progress-bar-fill-success';
  };

  return (
    <div className="flex-1 p-6 space-y-6 overflow-y-auto">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-ink-primary flex items-center gap-2">
          <Terminal className="w-5 h-5 text-accent-primary" />
          {t('nav.servers')}
        </h1>
        <p className="text-xs text-ink-secondary mt-1">
          {t('dash.servers_online', { online: nodes.filter((n) => n.online).length, total: nodes.length })}
        </p>
      </div>

      {/* Controls: Search + Status Filter */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface-0 border border-border p-4 rounded-lg">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-muted pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher par nom, hôte, OS..."
            className="input pl-9"
          />
        </div>

        {/* Status Filters */}
        <div className="flex items-center gap-1.5 self-start sm:self-auto">
          <button
            onClick={() => setStatusFilter('all')}
            className={`btn py-1.5 px-3 text-xs ${
              statusFilter === 'all'
                ? 'btn-primary'
                : 'btn-secondary'
            }`}
          >
            Tous
          </button>
          <button
            onClick={() => setStatusFilter('online')}
            className={`btn py-1.5 px-3 text-xs ${
              statusFilter === 'online'
                ? 'btn-primary'
                : 'btn-secondary'
            }`}
          >
            En ligne
          </button>
          <button
            onClick={() => setStatusFilter('offline')}
            className={`btn py-1.5 px-3 text-xs ${
              statusFilter === 'offline'
                ? 'btn-primary'
                : 'btn-secondary'
            }`}
          >
            Hors ligne
          </button>
        </div>
      </div>

      {/* Servers Table Card */}
      <div className="bg-surface-0 border border-border rounded-lg overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-border text-[0.6875rem] font-bold text-ink-muted uppercase tracking-wider bg-surface-1 select-none">
                <th
                  onClick={() => handleSort('name')}
                  className="px-4 py-3.5 cursor-pointer hover:text-ink-primary transition-colors"
                >
                  <div className="flex items-center gap-1">
                    <span>Serveur</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('online')}
                  className="px-4 py-3.5 cursor-pointer hover:text-ink-primary transition-colors w-24"
                >
                  <div className="flex items-center gap-1">
                    <span>Statut</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="px-4 py-3.5 text-[0.6875rem] font-bold">OS / Arch</th>
                <th
                  onClick={() => handleSort('cpu')}
                  className="px-4 py-3.5 cursor-pointer hover:text-ink-primary transition-colors w-28"
                >
                  <div className="flex items-center gap-1">
                    <span>CPU</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('mem')}
                  className="px-4 py-3.5 cursor-pointer hover:text-ink-primary transition-colors w-28"
                >
                  <div className="flex items-center gap-1">
                    <span>RAM</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('disk')}
                  className="px-4 py-3.5 cursor-pointer hover:text-ink-primary transition-colors w-28"
                >
                  <div className="flex items-center gap-1">
                    <span>Disque</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('containers')}
                  className="px-4 py-3.5 cursor-pointer hover:text-ink-primary transition-colors w-28 text-center"
                >
                  <div className="flex items-center gap-1 justify-center">
                    <span>Conteneurs</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('uptime')}
                  className="px-4 py-3.5 cursor-pointer hover:text-ink-primary transition-colors w-24"
                >
                  <div className="flex items-center gap-1">
                    <span>Uptime</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="px-4 py-3.5 text-right w-28">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border text-xs text-ink-primary">
              {isLoading && filteredNodes.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-ink-muted">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-accent-primary" />
                    Chargement des serveurs...
                  </td>
                </tr>
              ) : filteredNodes.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-ink-muted">
                    Aucun serveur trouvé.
                  </td>
                </tr>
              ) : (
                filteredNodes.map((node) => {
                  const metrics = nodeMetrics[node.id];
                  const hasMetrics = node.online && metrics && !metrics.loading;

                  return (
                    <tr
                      key={node.id}
                      onClick={() => navigate(`/nodes/${node.id}`)}
                      className="hover:bg-surface-1 cursor-pointer transition-colors duration-150 group"
                    >
                      {/* Name / Hostname */}
                      <td className="px-4 py-3">
                        <div className="font-semibold text-ink-primary group-hover:text-accent-primary transition-colors">
                          {node.name}
                        </div>
                        <div className="text-[0.625rem] font-mono text-ink-secondary truncate max-w-[150px]">
                          {node.hostname || 'N/A'}
                        </div>
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3">
                        {node.online ? (
                          <span className="badge badge-success text-[0.625rem]">
                            En ligne
                          </span>
                        ) : (
                          <span className="badge badge-subtle text-[0.625rem]">
                            Hors ligne
                          </span>
                        )}
                      </td>

                      {/* OS / Arch */}
                      <td className="px-4 py-3">
                        <div className="capitalize">{node.os || 'N/A'}</div>
                        <div className="text-[0.625rem] text-ink-secondary font-mono">
                          {node.arch || ''}
                        </div>
                      </td>

                      {/* CPU */}
                      <td className="px-4 py-3">
                        {hasMetrics ? (
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[0.625rem]">
                              <span className="font-medium">{metrics.cpu}%</span>
                            </div>
                            <div className="progress-bar-track">
                              <div
                                className={`progress-bar-fill ${getMetricColorClass(metrics.cpu)}`}
                                style={{ width: `${metrics.cpu}%` }}
                              />
                            </div>
                          </div>
                        ) : (
                          <span className="text-ink-muted font-mono">—</span>
                        )}
                      </td>

                      {/* RAM */}
                      <td className="px-4 py-3">
                        {hasMetrics ? (
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[0.625rem]">
                              <span className="font-medium">{metrics.mem}%</span>
                            </div>
                            <div className="progress-bar-track">
                              <div
                                className={`progress-bar-fill ${getMetricColorClass(metrics.mem)}`}
                                style={{ width: `${metrics.mem}%` }}
                              />
                            </div>
                          </div>
                        ) : (
                          <span className="text-ink-muted font-mono">—</span>
                        )}
                      </td>

                      {/* Disk */}
                      <td className="px-4 py-3">
                        {hasMetrics ? (
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[0.625rem]">
                              <span className="font-medium">{metrics.disk}%</span>
                            </div>
                            <div className="progress-bar-track">
                              <div
                                className={`progress-bar-fill ${getMetricColorClass(metrics.disk)}`}
                                style={{ width: `${metrics.disk}%` }}
                              />
                            </div>
                          </div>
                        ) : (
                          <span className="text-ink-muted font-mono">—</span>
                        )}
                      </td>

                      {/* Active Containers */}
                      <td className="px-4 py-3 text-center">
                        {hasMetrics ? (
                          <span className="font-bold text-ink-primary bg-surface-2 px-2 py-0.5 rounded border border-border">
                            {metrics.containersCount}
                          </span>
                        ) : (
                          <span className="text-ink-muted font-mono">—</span>
                        )}
                      </td>

                      {/* Uptime */}
                      <td className="px-4 py-3 font-mono text-[0.6875rem] text-ink-secondary">
                        {hasMetrics ? metrics.uptime : '—'}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {isAdmin && node.online && (
                            <button
                              onClick={(e) => handleRegenerateProfile(node.id, e)}
                              disabled={regeneratingMap[node.id]}
                              className="btn btn-ghost py-1 px-2 text-[0.625rem]"
                              title="Regénérer le profil d'insights IA"
                            >
                              <Activity className={`w-3 h-3 ${regeneratingMap[node.id] ? 'animate-spin' : ''}`} />
                            </button>
                          )}
                          <ChevronRight className="w-4 h-4 text-ink-muted group-hover:text-accent-primary group-hover:translate-x-0.5 transition-all duration-150" />
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
