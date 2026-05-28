import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link, useNavigate, useSearchParams } from 'react-router';
import { useNodeStore } from '../store/nodeStore';
import { useAuthStore } from '../store/authStore';
import { useToastStore } from '../store/useToastStore';
import { UptimeTracker } from '../components/ui/UptimeTracker';
import { useLocale } from '../i18n';
import { api } from '../hooks/useApi';
import { 
  ArrowLeft, 
  Activity, 
  Cpu, 
  HardDrive, 
  Terminal, 
  RotateCw, 
  Trash2, 
  AlertTriangle,
  Layers,
  Search,
  Sliders,
  Loader2
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip 
} from 'recharts';

type TabType = 'metrics' | 'services' | 'containers' | 'logs';

export const NodeDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabQuery = searchParams.get('tab') as TabType | null;
  const { t } = useLocale();
  
  const { selectNode } = useNodeStore();
  const { accessToken, user } = useAuthStore();

  const [activeTab, setActiveTab] = useState<TabType>('metrics');

  useEffect(() => {
    if (tabQuery && ['metrics', 'services', 'containers', 'logs'].includes(tabQuery)) {
      setActiveTab(tabQuery);
    }
  }, [tabQuery]);

  const [nodeDetail, setNodeDetail] = useState<any>(null);
  const [isLoadingNode, setIsLoadingNode] = useState(true);
  const [nodeError, setNodeError] = useState<string | null>(null);

  // Stats/Metrics state
  const [statsSnapshots, setStatsSnapshots] = useState<any[]>([]);
  const [statsLimit, setStatsLimit] = useState(30);
  const [isLoadingStats, setIsLoadingStats] = useState(false);

  // Services state
  const [services, setServices] = useState<any[]>([]);
  const [servicesSearch, setServicesSearch] = useState('');
  const [isLoadingServices, setIsLoadingServices] = useState(false);
  const [serviceActionLoading, setServiceActionLoading] = useState<string | null>(null);

  // Containers state
  const [containers, setContainers] = useState<any[]>([]);
  const [containersSearch, setContainersSearch] = useState('');
  const [isLoadingContainers, setIsLoadingContainers] = useState(false);
  const [containerActionLoading, setContainerActionLoading] = useState<string | null>(null);

  // Logs state
  const [logOutput, setLogOutput] = useState('');
  const [logLines, setLogLines] = useState(100);
  const [logService, setLogService] = useState('');
  const [logPath, setLogPath] = useState('/var/log/syslog');
  const [logMode, setLogMode] = useState<'service' | 'file'>('file');
  const [isLoadingLogs, setIsLoadingLogs] = useState(false);

  // Confirmations
  const [showRevokeModal, setShowRevokeModal] = useState(false);
  const [isRevoking, setIsRevoking] = useState(false);

  const isAdmin = user?.role === 'admin';
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // 1. Fetch Node detail on mount / change
  const fetchNodeDetail = async () => {
    if (!id) return;
    setIsLoadingNode(true);
    setNodeError(null);
    try {
      const data = await api<any>(`/api/nodes/${id}`);
      if (data) {
        setNodeDetail(data);
        selectNode(data.id); // Sync with store
      } else {
        throw new Error(t('error.load_data'));
      }
    } catch (err: any) {
      setNodeError(err.message || t('error.load_data'));
    } finally {
      setIsLoadingNode(false);
    }
  };

  useEffect(() => {
    fetchNodeDetail();
  }, [id, accessToken]);

  // 2. Fetch Metrics Snapshots
  const fetchMetrics = async () => {
    if (!id || !accessToken) return;
    setIsLoadingStats(true);
    try {
      const data = await api<any>(`/api/nodes/${id}/stats?limit=${statsLimit}`);
      if (data && data.snapshots) {
        // Recharts needs time chronological order (API returns desc)
        const sortedSnaps = [...(data.snapshots || [])].reverse();
        setStatsSnapshots(sortedSnaps);
      }
    } catch (e) {
      console.error("Error fetching stats snapshots", e);
    } finally {
      setIsLoadingStats(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'metrics' && nodeDetail?.online) {
      fetchMetrics();
      const interval = setInterval(fetchMetrics, 10000); // refresh stats every 10s
      return () => clearInterval(interval);
    }
  }, [id, activeTab, nodeDetail?.online, statsLimit, accessToken]);

  // 3. Fetch Services
  const fetchServicesList = async () => {
    if (!id || !nodeDetail?.online) return;
    setIsLoadingServices(true);
    try {
      const data = await api<any>(`/api/nodes/${id}/services`);
      if (data && data.services) {
        setServices(data.services);
      }
    } catch (e) {
      console.error("Error fetching services list", e);
    } finally {
      setIsLoadingServices(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'services' && nodeDetail?.online) {
      fetchServicesList();
    }
  }, [id, activeTab, nodeDetail?.online]);

  // 4. Fetch Containers
  const fetchContainersList = async () => {
    if (!id || !nodeDetail?.online) return;
    setIsLoadingContainers(true);
    try {
      const data = await api<any>(`/api/nodes/${id}/containers`);
      if (data && data.containers) {
        setContainers(data.containers);
      }
    } catch (e) {
      console.error("Error fetching containers list", e);
    } finally {
      setIsLoadingContainers(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'containers' && nodeDetail?.online) {
      fetchContainersList();
    }
  }, [id, activeTab, nodeDetail?.online]);

  // 5. Fetch Logs
  const fetchLogs = async () => {
    if (!id || !nodeDetail?.online) return;
    setIsLoadingLogs(true);
    setLogOutput('');
    try {
      let url = `/api/nodes/${id}/logs?lines=${logLines}`;
      if (logMode === 'service') {
        if (!logService.trim()) {
          useToastStore.getState().addToast('error', 'Erreur', 'Le nom du service est requis.');
          setIsLoadingLogs(false);
          return;
        }
        url += `&service=${encodeURIComponent(logService.trim())}`;
      } else {
        if (!logPath.trim()) {
          useToastStore.getState().addToast('error', 'Erreur', 'Le chemin du fichier de logs est requis.');
          setIsLoadingLogs(false);
          return;
        }
        url += `&path=${encodeURIComponent(logPath.trim())}`;
      }

      const data = await api<any>(url);
      if (data) {
        if (data.error) {
          throw new Error(data.error);
        }
        setLogOutput(data.output || 'Aucun log trouvé.');
        setTimeout(() => {
          terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      }
    } catch (e: any) {
      setLogOutput(`[ERREUR] ${e.message}`);
      useToastStore.getState().addToast('error', 'Erreur', e.message);
    } finally {
      setIsLoadingLogs(false);
    }
  };

  // Restart Service Action (Admin only)
  const handleRestartService = async (serviceName: string) => {
    if (!id || !isAdmin) return;
    setServiceActionLoading(serviceName);
    try {
      const data = await api<any>(`/api/nodes/${id}/services/${serviceName}/restart`, {
        method: 'POST'
      });
      if (data) {
        if (data.error) {
          useToastStore.getState().addToast('error', 'Erreur', `Erreur: ${data.error}`);
        } else {
          useToastStore.getState().addToast('success', 'Succès', `Service ${serviceName} redémarré avec succès !`);
          fetchServicesList(); // Refresh
        }
      }
    } catch (e: any) {
      useToastStore.getState().addToast('error', 'Erreur', e.message || 'Une erreur inattendue est survenue.');
    } finally {
      setServiceActionLoading(null);
    }
  };

  // Restart Container Action (Admin only)
  const handleRestartContainer = async (containerId: string) => {
    if (!id || !isAdmin) return;
    setContainerActionLoading(containerId);
    try {
      const data = await api<any>(`/api/nodes/${id}/containers/${containerId}/restart`, {
        method: 'POST'
      });
      if (data) {
        if (data.error) {
          useToastStore.getState().addToast('error', 'Erreur', `Erreur: ${data.error}`);
        } else {
          useToastStore.getState().addToast('success', 'Succès', 'Conteneur redémarré avec succès !');
          fetchContainersList(); // Refresh
        }
      }
    } catch (e: any) {
      useToastStore.getState().addToast('error', 'Erreur', e.message || 'Une erreur inattendue est survenue.');
    } finally {
      setContainerActionLoading(null);
    }
  };

  // Revoke Node Action (Admin only)
  const handleRevokeNode = async () => {
    if (!id || !isAdmin || isRevoking) return;
    setIsRevoking(true);
    try {
      await api<any>(`/api/nodes/${id}`, {
        method: 'DELETE'
      });
      setShowRevokeModal(false);
      useToastStore.getState().addToast('success', 'Succès', 'Serveur révoqué avec succès !');
      navigate('/');
    } catch (e: any) {
      useToastStore.getState().addToast('error', 'Erreur', e.message || 'Impossible de révoquer le serveur');
    } finally {
      setIsRevoking(false);
    }
  };

  // Filters
  const filteredServices = services.filter(s => 
    s.service.toLowerCase().includes(servicesSearch.toLowerCase()) ||
    s.active.toLowerCase().includes(servicesSearch.toLowerCase()) ||
    s.description?.toLowerCase().includes(servicesSearch.toLowerCase())
  );

  const filteredContainers = containers.filter(c => 
    c.name.toLowerCase().includes(containersSearch.toLowerCase()) ||
    c.image.toLowerCase().includes(containersSearch.toLowerCase()) ||
    c.state.toLowerCase().includes(containersSearch.toLowerCase())
  );

  // Time conversion helpers
  const formatTime = (epochSeconds: number | null) => {
    if (!epochSeconds) return 'Jamais';
    return new Date(epochSeconds * 1000).toLocaleString('fr-FR');
  };

  const chartData = statsSnapshots.map(snap => ({
    time: new Date(snap.collected_at * 1000).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
    cpu: Math.round(snap.cpu_percent),
    ram: Math.round(snap.mem_percent),
    disk: Math.round(snap.disk_percent)
  }));

  const latestStats = statsSnapshots[statsSnapshots.length - 1] || null;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Top Breadcrumb & Actions */}
      <div className="flex items-center justify-between border-b border-border/40 pb-5">
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="btn btn-secondary py-1.5 px-3"
            aria-label="Retour au tableau de bord"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-ink-primary tracking-tight">
                {isLoadingNode ? 'Chargement...' : nodeDetail?.name}
              </h1>
              {nodeDetail && (
                <span className={`w-2.5 h-2.5 rounded-full ${nodeDetail.online ? 'bg-success shadow-[0_0_8px_var(--color-success)]' : 'bg-ink-muted'}`} />
              )}
            </div>
            <p className="text-[10px] text-ink-muted font-mono mt-0.5 max-w-sm truncate" title={id}>
              ID: {id}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {nodeDetail?.online && (
            <button
              onClick={() => {
                if (activeTab === 'metrics') fetchMetrics();
                else if (activeTab === 'services') fetchServicesList();
                else if (activeTab === 'containers') fetchContainersList();
                else if (activeTab === 'logs') fetchLogs();
              }}
              className="btn btn-secondary text-xs"
              aria-label="Actualiser les données"
            >
              <RotateCw className="w-3.5 h-3.5" />
              <span>Actualiser</span>
            </button>
          )}

          {isAdmin && (
            <button
              onClick={() => setShowRevokeModal(true)}
              className="btn btn-danger text-xs"
              aria-label="Révoquer ce serveur"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Révoquer le serveur</span>
            </button>
          )}
        </div>
      </div>

      {isLoadingNode ? (
        <div className="card p-20 flex flex-col items-center justify-center">
          <Loader2 className="w-8 h-8 text-accent-primary animate-spin mb-3" />
          <p className="text-xs text-ink-muted">Chargement de la configuration du serveur...</p>
        </div>
      ) : nodeError ? (
        <div className="card p-10 text-center max-w-xl mx-auto space-y-4">
          <AlertTriangle className="w-10 h-10 text-danger mx-auto" />
          <h2 className="text-sm font-bold text-ink-primary">Impossible d'afficher le serveur</h2>
          <p className="text-xs text-ink-secondary">{nodeError}</p>
          <Link
            to="/"
            className="btn btn-secondary text-xs"
          >
            Retour au tableau de bord
          </Link>
        </div>
      ) : (
        <>
          {/* Node Summary Card */}
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
            <div className="card p-4 space-y-1">
              <span className="text-[10px] font-bold text-ink-muted uppercase tracking-wider">État opérationnel</span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`w-2 h-2 rounded-full ${nodeDetail.online ? 'bg-success shadow-[0_0_6px_var(--color-success)]' : 'bg-ink-muted'}`} />
                <span className="text-xs font-bold text-ink-primary">
                  {nodeDetail.online ? 'En ligne' : 'Hors-ligne'}
                </span>
                <span className="badge badge-subtle ml-2 font-mono">
                  {nodeDetail.state}
                </span>
              </div>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[10px] font-bold text-ink-muted uppercase tracking-wider">Système d'exploitation / Arch</span>
              <div className="text-xs font-bold text-ink-primary mt-0.5 truncate uppercase">
                {nodeDetail.os || 'Inconnu'} / {nodeDetail.arch || 'Inconnu'}
              </div>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[10px] font-bold text-ink-muted uppercase tracking-wider">Date d'ajout</span>
              <div className="text-xs font-bold text-ink-primary mt-0.5">
                {formatTime(nodeDetail.enrolled_at)}
              </div>
            </div>

            <div className="card p-4 space-y-1">
              <span className="text-[10px] font-bold text-ink-muted uppercase tracking-wider">Dernier Heartbeat</span>
              <div className="text-xs font-bold text-ink-primary mt-0.5">
                {formatTime(nodeDetail.last_heartbeat)}
              </div>
            </div>
          </div>

          {/* Uptime Status Tracker */}
          <UptimeTracker nodeId={nodeDetail.id} isOnline={nodeDetail.online} />

          {/* Offline Warning Banner */}
          {!nodeDetail.online && (
            <div className="p-3 bg-danger-subtle border border-danger/20 rounded text-xs text-danger flex items-center gap-2 font-medium">
              <AlertTriangle className="w-4 h-4 shrink-0 animate-pulse" />
              <span>Le serveur est actuellement hors-ligne. Les requêtes en temps réel (services, conteneurs, logs en direct) sont temporairement désactivées.</span>
            </div>
          )}

          {/* Navigation Tabs */}
          <div className="flex border-b border-border shrink-0 overflow-x-auto gap-2">
            {[
              { id: 'metrics', label: 'Métriques', icon: Activity },
              { id: 'services', label: 'Services Systemd', icon: Sliders },
              { id: 'containers', label: 'Docker', icon: Layers },
              { id: 'logs', label: 'Journaux / Logs', icon: Terminal }
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setSearchParams({ tab: tab.id })}
                  className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 cursor-pointer transition-all duration-150 ${
                    isActive
                      ? 'border-accent-primary text-accent-primary bg-accent-subtle'
                      : 'border-transparent text-ink-muted hover:text-ink-primary hover:bg-surface-1'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Tab Panels */}
          <div className="space-y-6">
            {/* TAB: METRICS */}
            {activeTab === 'metrics' && (
              <div className="space-y-6">
                {isLoadingStats && statsSnapshots.length === 0 ? (
                  <div className="card p-20 text-center">
                    <Loader2 className="w-6 h-6 text-accent-primary animate-spin mx-auto mb-2" />
                    <span className="text-xs text-ink-muted">Chargement des métriques...</span>
                  </div>
                ) : statsSnapshots.length === 0 ? (
                  <div className="card p-10 text-center italic text-xs text-ink-muted">
                    Aucun historique de métriques trouvé.
                  </div>
                ) : (
                  <>
                    {/* Live Resource Meters */}
                    {latestStats && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* CPU */}
                        <div className="card p-5 space-y-4">
                          <div className="flex justify-between items-center">
                            <span className="text-xs font-bold text-ink-primary flex items-center gap-1.5">
                              <Cpu className="w-4 h-4 text-accent-primary" />
                              <span>Utilisation CPU</span>
                            </span>
                            <span className="text-lg font-bold text-ink-primary font-mono">{Math.round(latestStats.cpu_percent)}%</span>
                          </div>
                          <div className="progress-bar-track">
                            <div className="progress-bar-fill progress-bar-fill-success" style={{ width: `${latestStats.cpu_percent}%` }} />
                          </div>
                          <div className="flex justify-between text-[10px] text-ink-secondary font-mono">
                            <span>Cœurs : {latestStats.cpu_cores || 'N/A'}</span>
                            <span>Charge 1m : {latestStats.cpu_load_1m || '0.00'}</span>
                          </div>
                        </div>

                        {/* RAM */}
                        <div className="card p-5 space-y-4">
                          <div className="flex justify-between items-center">
                            <span className="text-xs font-bold text-ink-primary flex items-center gap-1.5">
                              <Cpu className="w-4 h-4 text-accent-primary" />
                              <span>Utilisation Mémoire</span>
                            </span>
                            <span className="text-lg font-bold text-ink-primary font-mono">{Math.round(latestStats.mem_percent)}%</span>
                          </div>
                          <div className="progress-bar-track">
                            <div className="progress-bar-fill progress-bar-fill-success" style={{ width: `${latestStats.mem_percent}%` }} />
                          </div>
                          <div className="flex justify-between text-[10px] text-ink-secondary font-mono">
                            <span>Utilisé : {(latestStats.mem_used_bytes / (1024 ** 3)).toFixed(2)} Go</span>
                            <span>Total : {(latestStats.mem_total_bytes / (1024 ** 3)).toFixed(2)} Go</span>
                          </div>
                        </div>

                        {/* Disk */}
                        <div className="card p-5 space-y-4">
                          <div className="flex justify-between items-center">
                            <span className="text-xs font-bold text-ink-primary flex items-center gap-1.5">
                              <HardDrive className="w-4 h-4 text-accent-primary" />
                              <span>Utilisation Disque</span>
                            </span>
                            <span className="text-lg font-bold text-ink-primary font-mono">{Math.round(latestStats.disk_percent)}%</span>
                          </div>
                          <div className="progress-bar-track">
                            <div className="progress-bar-fill progress-bar-fill-success" style={{ width: `${latestStats.disk_percent}%` }} />
                          </div>
                          <div className="flex justify-between text-[10px] text-ink-secondary font-mono">
                            <span>Utilisé : {(latestStats.disk_used_bytes / (1024 ** 3)).toFixed(1)} Go</span>
                            <span>Total : {(latestStats.disk_total_bytes / (1024 ** 3)).toFixed(1)} Go</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Chart Container */}
                    <div className="card p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-1.5">
                          <Activity className="w-4 h-4 text-accent-primary" />
                          <span>Historique d'activité</span>
                        </h3>
                        <div className="flex gap-1.5">
                          {[10, 30, 50, 100].map(val => (
                            <button
                              key={val}
                              onClick={() => setStatsLimit(val)}
                              className={`btn text-[10px] py-0.5 px-2 ${
                                statsLimit === val 
                                  ? 'btn-primary' 
                                  : 'btn-secondary'
                              }`}
                            >
                              {val} snaps
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="h-80 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <defs>
                              <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="var(--color-accent-primary)" stopOpacity={0.2}/>
                                <stop offset="95%" stopColor="var(--color-accent-primary)" stopOpacity={0.0}/>
                              </linearGradient>
                              <linearGradient id="ramGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="var(--color-success)" stopOpacity={0.2}/>
                                <stop offset="95%" stopColor="var(--color-success)" stopOpacity={0.0}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.3} />
                            <XAxis dataKey="time" stroke="var(--color-ink-muted)" fontSize={9} />
                            <YAxis stroke="var(--color-ink-muted)" fontSize={9} domain={[0, 100]} />
                            <Tooltip 
                              contentStyle={{ 
                                backgroundColor: 'var(--color-surface-1)', 
                                border: '1px solid var(--color-border)',
                                borderRadius: 'var(--radius-md)',
                                fontSize: '11px',
                                color: 'var(--color-ink-primary)'
                              }}
                            />
                            <Area type="monotone" dataKey="cpu" name="CPU (%)" stroke="var(--color-accent-primary)" strokeWidth={1.5} fillOpacity={1} fill="url(#cpuGrad)" />
                            <Area type="monotone" dataKey="ram" name="Mémoire (%)" stroke="var(--color-success)" strokeWidth={1.5} fillOpacity={1} fill="url(#ramGrad)" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* TAB: SERVICES */}
            {activeTab === 'services' && (
              <div className="card p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2">
                  <div>
                    <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider">
                      Services Systemd
                    </h3>
                    <p className="text-[10px] text-ink-secondary mt-0.5">
                      Gérez les services système déclarés sur le démon systemd du serveur.
                    </p>
                  </div>
                  <div className="relative w-full sm:w-60 shrink-0">
                    <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
                    <input
                      type="text"
                      value={servicesSearch}
                      onChange={(e) => setServicesSearch(e.target.value)}
                      placeholder="Rechercher un service..."
                      className="input pl-9 text-xs"
                    />
                  </div>
                </div>

                {isLoadingServices ? (
                  <div className="p-12 text-center">
                    <Loader2 className="w-6 h-6 text-accent-primary animate-spin mx-auto mb-2" />
                    <span className="text-xs text-ink-muted">Récupération de la liste des services systemd...</span>
                  </div>
                ) : filteredServices.length === 0 ? (
                  <div className="p-8 text-center italic text-xs text-ink-secondary bg-surface-1 border border-border rounded">
                    Aucun service systemd trouvé ou correspondant aux critères.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-border text-ink-muted text-[10px] uppercase font-bold tracking-wider">
                          <th className="py-2.5 px-3">Service</th>
                          <th className="py-2.5 px-3">Actif</th>
                          <th className="py-2.5 px-3">Démarrage</th>
                          <th className="py-2.5 px-3">Description</th>
                          {isAdmin && <th className="py-2.5 px-3 text-right">Actions</th>}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40">
                        {filteredServices.map((srv, idx) => {
                          const isActive = srv.active === 'active';
                          const isFailed = srv.sub === 'failed' || srv.active === 'failed';

                          return (
                            <tr key={idx} className="hover:bg-surface-1 transition-colors">
                              <td className="py-2.5 px-3 font-mono font-semibold text-ink-primary">
                                {srv.service}
                              </td>
                              <td className="py-2.5 px-3">
                                <span className={`badge ${
                                  isActive ? 'badge-success' :
                                  isFailed ? 'badge-danger' :
                                  'badge-subtle'
                                } flex items-center gap-1`}>
                                  <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-success' : isFailed ? 'bg-danger' : 'bg-ink-muted'}`} />
                                  <span>{srv.active}</span>
                                </span>
                              </td>
                              <td className="py-2.5 px-3 font-mono text-ink-secondary">
                                {srv.enabled || 'unknown'}
                              </td>
                              <td className="py-2.5 px-3 text-ink-secondary max-w-xs truncate" title={srv.description}>
                                {srv.description}
                              </td>
                              {isAdmin && (
                                <td className="py-2 px-3 text-right">
                                  <button
                                    onClick={() => handleRestartService(srv.service)}
                                    disabled={serviceActionLoading !== null}
                                    className="btn btn-secondary py-1 px-2 border-border/50 text-ink-secondary hover:text-ink-primary disabled:opacity-40"
                                    title="Redémarrer le service"
                                    aria-label={`Restart service ${srv.service}`}
                                  >
                                    {serviceActionLoading === srv.service ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                      <RotateCw className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                </td>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* TAB: DOCKER */}
            {activeTab === 'containers' && (
              <div className="card p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2">
                  <div>
                    <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-1.5">
                      <Layers className="w-4 h-4 text-accent-primary" />
                      <span>Conteneurs Docker</span>
                    </h3>
                    <p className="text-[10px] text-ink-secondary mt-0.5">
                      Supervisez les charges applicatives isolées via le socket Docker UNIX.
                    </p>
                  </div>
                  <div className="relative w-full sm:w-60 shrink-0">
                    <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
                    <input
                      type="text"
                      value={containersSearch}
                      onChange={(e) => setContainersSearch(e.target.value)}
                      placeholder="Rechercher un conteneur..."
                      className="input pl-9 text-xs"
                    />
                  </div>
                </div>

                {isLoadingContainers ? (
                  <div className="p-12 text-center">
                    <Loader2 className="w-6 h-6 text-accent-primary animate-spin mx-auto mb-2" />
                    <span className="text-xs text-ink-muted">Récupération de la liste des conteneurs...</span>
                  </div>
                ) : filteredContainers.length === 0 ? (
                  <div className="p-8 text-center italic text-xs text-ink-secondary bg-surface-1 border border-border rounded">
                    Aucun conteneur Docker actif ou trouvé sur la machine.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="border-b border-border text-ink-muted text-[10px] uppercase font-bold tracking-wider">
                          <th className="py-2.5 px-3">Nom</th>
                          <th className="py-2.5 px-3">ID / Image</th>
                          <th className="py-2.5 px-3">Statut</th>
                          <th className="py-2.5 px-3">Créé</th>
                          <th className="py-2.5 px-3">Ports</th>
                          {isAdmin && <th className="py-2.5 px-3 text-right">Actions</th>}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40">
                        {filteredContainers.map((c, idx) => {
                          const isRunning = c.state === 'running' || c.status?.toLowerCase().includes('up');
                          return (
                            <tr key={idx} className="hover:bg-surface-1 transition-colors">
                              <td className="py-2.5 px-3 font-semibold text-ink-primary">
                                {c.name}
                              </td>
                              <td className="py-2.5 px-3">
                                <div className="font-mono text-[10px] text-ink-muted">ID: {c.id?.substring(0, 12)}</div>
                                <div className="text-[10px] text-ink-secondary truncate max-w-[200px]" title={c.image}>{c.image}</div>
                              </td>
                              <td className="py-2.5 px-3">
                                <span className={`badge ${
                                  isRunning ? 'badge-success' : 'badge-subtle'
                                } flex items-center gap-1`}>
                                  <span className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-success' : 'bg-ink-muted'}`} />
                                  <span>{c.state || c.status}</span>
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-ink-secondary font-mono text-[10px]">
                                {c.created || 'unknown'}
                              </td>
                              <td className="py-2.5 px-3 text-ink-secondary font-mono text-[10px] max-w-[150px] truncate" title={c.ports}>
                                {c.ports || '-'}
                              </td>
                              {isAdmin && (
                                <td className="py-2 px-3 text-right">
                                  <button
                                    onClick={() => handleRestartContainer(c.id)}
                                    disabled={containerActionLoading !== null}
                                    className="btn btn-secondary py-1 px-2 border-border/50 text-ink-secondary hover:text-ink-primary disabled:opacity-40"
                                    title="Redémarrer le conteneur"
                                    aria-label={`Restart container ${c.name}`}
                                  >
                                    {containerActionLoading === c.id ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                      <RotateCw className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                </td>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* TAB: LOGS */}
            {activeTab === 'logs' && (
              <div className="space-y-4">
                {/* Filters Block */}
                <div className="card p-4 flex flex-col md:flex-row gap-4 items-end">
                  <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-4 w-full">
                    {/* Log Mode selection */}
                    <div className="space-y-1">
                      <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Mode de lecture</label>
                      <div className="flex rounded border border-border overflow-hidden bg-surface-1 p-0.5">
                        <button
                          onClick={() => setLogMode('file')}
                          className={`flex-1 py-1 text-[10px] font-bold rounded cursor-pointer transition-colors ${logMode === 'file' ? 'bg-surface-2 text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
                        >
                          Fichier log
                        </button>
                        <button
                          onClick={() => setLogMode('service')}
                          className={`flex-1 py-1 text-[10px] font-bold rounded cursor-pointer transition-colors ${logMode === 'service' ? 'bg-surface-2 text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'}`}
                        >
                          Journal Journalctl
                        </button>
                      </div>
                    </div>

                    {/* Dynamic input based on mode */}
                    {logMode === 'file' ? (
                      <div className="space-y-1">
                        <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Chemin du fichier</label>
                        <input
                          type="text"
                          value={logPath}
                          onChange={(e) => setLogPath(e.target.value)}
                          placeholder="/var/log/syslog"
                          className="input"
                        />
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Nom du service systemd</label>
                        <input
                          type="text"
                          value={logService}
                          onChange={(e) => setLogService(e.target.value)}
                          placeholder="nginx.service"
                          className="input"
                        />
                      </div>
                    )}

                    {/* Lines count */}
                    <div className="space-y-1">
                      <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Lignes à récupérer</label>
                      <select
                        value={logLines}
                        onChange={(e) => setLogLines(Number(e.target.value))}
                        className="select"
                      >
                        {[10, 50, 100, 200, 500].map(val => (
                          <option key={val} value={val}>{val} lignes</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <button
                    onClick={fetchLogs}
                    disabled={isLoadingLogs}
                    className="btn btn-primary h-[34px] w-full md:w-auto"
                    aria-label="Charger les logs du serveur"
                  >
                    {isLoadingLogs ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <>
                        <Terminal className="w-3.5 h-3.5" />
                        <span>Charger les logs</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Log Terminal display */}
                <div className="card p-0 bg-[#06060a] border border-border flex flex-col h-[400px]">
                  <div className="h-8 border-b border-border/80 bg-surface-1 px-4 flex items-center justify-between text-[10px] text-ink-muted font-bold tracking-wider shrink-0 select-none">
                    <span className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-danger" />
                      <span className="w-2 h-2 rounded-full bg-warning" />
                      <span className="w-2 h-2 rounded-full bg-success" />
                      <span className="ml-2 font-mono text-[9px] text-ink-secondary">{logMode === 'file' ? logPath : `journalctl -u ${logService}`}</span>
                    </span>
                    <span className="text-ink-secondary font-mono text-[9px]">Bash Console logs</span>
                  </div>

                  <div className="flex-1 p-4 overflow-y-auto font-mono text-[11px] leading-relaxed text-success/90 space-y-1 select-text scrollbar-thin">
                    {logOutput ? (
                      logOutput.split('\n').map((line, idx) => (
                        <div key={idx} className="whitespace-pre-wrap break-all hover:bg-white/5 px-1 py-0.5 rounded transition-colors">
                          {line}
                        </div>
                      ))
                    ) : (
                      <div className="text-ink-muted italic py-10 text-center select-none">
                        Cliquez sur "Charger les logs" pour afficher les journaux d'activité en direct.
                      </div>
                    )}
                    <div ref={terminalEndRef} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* MODAL: REVOKE SERVER CONFIRMATION */}
      {showRevokeModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-in select-none">
          <div className="w-full max-w-md card p-6 shadow-2xl space-y-5 animate-fade-up">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-danger-subtle border border-danger/25 flex items-center justify-center text-danger">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-ink-primary uppercase tracking-wider">Révoquer le serveur</h3>
                <p className="text-[10px] text-danger font-semibold uppercase">Action irréversible et destructive</p>
              </div>
            </div>

            <p className="text-xs text-ink-secondary leading-relaxed">
              Êtes-vous sûr de vouloir révoquer le serveur <strong className="text-ink-primary font-semibold">{nodeDetail?.name}</strong> ? 
              Cette action coupera immédiatement sa connexion WebSocket active, détruira ses identifiants de connexion locaux et le déclarera révoqué à vie.
              Pour le reconnecter à l'avenir, vous devrez régénérer une commande d'installation et ré-exécuter le script kickstart.
            </p>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowRevokeModal(false)}
                disabled={isRevoking}
                className="btn btn-secondary text-xs"
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={handleRevokeNode}
                disabled={isRevoking}
                className="btn btn-danger text-xs flex items-center gap-1.5"
              >
                {isRevoking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                <span>Confirmer la Révocation</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
