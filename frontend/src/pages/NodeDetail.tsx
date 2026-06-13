import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useUiStore } from '../store/uiStore';
import { useNodeInsights } from '../hooks/useNodeInsights';
import { usePolling } from '../hooks/usePolling';
import { StatusDot } from '../components/primitives/StatusDot';
import { MetricPill } from '../components/primitives/MetricPill';
import { TimeAgo } from '../components/primitives/TimeAgo';
import { Spinner } from '../components/primitives/Spinner';
import { SeverityTag } from '../components/primitives/SeverityTag';
import { InsightText } from '../components/primitives/InsightText';
import { Badge } from '../components/primitives/Badge';
import { api } from '../hooks/useApi';
import { usePermission } from '../hooks/usePermission';
import { usePageTitle } from '../hooks/usePageTitle';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import {
  Cpu,
  Layers,
  ArrowLeft,
  RefreshCw,
  Search,
  Sparkles,
  Database,
  Calendar,
} from 'lucide-react';
import { formatOfflineDuration } from '../utils/formatTime';

const OfflineInsightCard: React.FC<{ insight: any; nodeId: string | undefined }> = ({ insight, nodeId }) => {
  const { openCopilot } = useUiStore();
  const [tick, setTick] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (!insight.raw?.last_heartbeat) return;

    const interval = setInterval(() => {
      setTick((t) => t + 1);
    }, 30000);
    return () => clearInterval(interval);
  }, [insight]);

  // Compute headline and detail dynamically on render to avoid cascading state updates
  let headline = insight.headline;
  let detail = insight.detail;
  if (insight.raw?.last_heartbeat) {
    const hbTime = insight.raw.last_heartbeat;
    const durationStr = formatOfflineDuration(hbTime);
    headline = `Hors-ligne depuis ${durationStr}`;
    const hbLabel = new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString('fr-FR');
    detail = `Dernier contact le ${hbLabel}. Vérifiez la connectivité réseau.`;
  }

  return (
    <div
      data-tick={tick}
      className={`p-5 border border-text-3/20 rounded-xl bg-surface hover:border-text-2/40 flex flex-col justify-between shadow-md transition-all group ${isExpanded ? '!h-auto' : 'h-52'}`}
      style={{ background: 'linear-gradient(135deg, rgba(92, 87, 112, 0.02), var(--surface))' }}
    >
      <div className="flex items-center justify-between gap-2 shrink-0">
        <SeverityTag severity="offline" className="whitespace-nowrap" />
        <span className="text-[8px] font-extrabold font-interface tracking-widest text-text-3 uppercase whitespace-nowrap">
          AI REPORT
        </span>
      </div>

      <div className="my-2.5 flex-1 flex flex-col justify-center min-w-0">
        <InsightText size="sm" className="block text-text-1 leading-snug font-serif !text-[16px] md:!text-[17px] line-clamp-2 group-hover:text-text-2 transition-colors" title={headline}>
          {headline}
        </InsightText>
        <p className={`text-text-3 text-[10px] font-sans mt-1 leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`} title={detail}>
          {detail}
          {detail.length > 80 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[9px]"
            >
              {isExpanded ? 'Moins' : 'Plus'}
            </button>
          )}
        </p>
      </div>

      <div className="pt-2 border-t border-border/40 flex items-center justify-between shrink-0">
        <span title="Assistant IA" className="flex items-center shrink-0">
          <Sparkles className="w-3.5 h-3.5 text-text-2 animate-pulse" />
        </span>
        <button
          onClick={() =>
            openCopilot({
              trigger: 'diagnostic',
              insight,
              node_id: nodeId,
            })
          }
          className="text-[10px] font-extrabold font-interface text-text-2 hover:underline flex items-center gap-0.5 cursor-pointer"
        >
          Diagnostiquer →
        </button>
      </div>
    </div>
  );
};

export const NodeDetail: React.FC = () => {
  usePageTitle('Détail du nœud');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const { isAdmin, can } = usePermission();
  const isAdminOrOperator = can('approve-action');

  const { openCopilot } = useUiStore();
  const { insights, loading: loadingInsights, refresh: refreshInsights } = useNodeInsights(id || null);

  // States
  const [node, setNode] = useState<any>(null);
  const [loadingNode, setLoadingNode] = useState(true);

  // Combine real insights with synthetic offline insight if node is offline
  const displayInsights = [...insights];
  if (node && !node.online) {
    const hbTime = node.last_heartbeat;
    const hbLabel = hbTime
      ? new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString('fr-FR')
      : null;

    displayInsights.unshift({
      type: 'offline',
      severity: 'offline' as const,
      icon: '📡',
      headline: hbTime
        ? `Hors-ligne — dernier contact ${hbLabel}`
        : 'Hors-ligne — aucun heartbeat enregistré',
      detail: hbTime
        ? `Dernier heartbeat reçu le ${hbLabel}. Vérifiez la connectivité réseau.`
        : 'Ce nœud n\'a jamais envoyé de heartbeat. Vérifiez l\'enrollment.',
      raw: {
        last_heartbeat: hbTime
      }
    });
  }

  const [activeTab, setActiveTab] = useState<'insights' | 'metrics' | 'services' | 'containers' | 'logs'>('insights');
  const [statsHistory, setStatsHistory] = useState<any[]>([]);
  const [loadingStats, setLoadingStats] = useState(false);

  // Services State
  const [services, setServices] = useState<any[]>([]);
  const [loadingServices, setLoadingServices] = useState(false);
  const [serviceFilter, setServiceFilter] = useState('');
  const [serviceSearch, setServiceSearch] = useState('');

  // Containers State
  const [containers, setContainers] = useState<any[]>([]);
  const [loadingContainers, setLoadingContainers] = useState(false);
  const [containerSearch, setContainerSearch] = useState('');

  // Logs State
  const [logs, setLogs] = useState<string>('');
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logsService, setLogsService] = useState<string>('');
  const [logsLimit, setLogsLimit] = useState<number>(100);
  const [logsAutoScroll, setLogsAutoScroll] = useState(true);
  const logsConsoleRef = useRef<HTMLDivElement>(null);

  // Operations actions loading states
  const [restartingService, setRestartingService] = useState<string | null>(null);
  const [restartingContainer, setRestartingContainer] = useState<string | null>(null);

  const fetchNodeDetails = async () => {
    if (!id) return;
    try {
      const data = await api<any>(`/api/nodes/${id}`);
      if (data) setNode(data);
    } catch (err) {
      console.error('Failed to fetch node:', err);
    }
  };

  const fetchStatsHistory = async () => {
    if (!id) return;
    setLoadingStats(true);
    try {
      const data = await api<{ snapshots: any[] }>(`/api/nodes/${id}/stats?limit=60`);
      if (data && data.snapshots) {
        // Reverse array to show chronological order (left-to-right)
        const ordered = [...data.snapshots].reverse().map((snap) => ({
          time: new Date(snap.collected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          cpu: snap.cpu_percent,
          ram: snap.mem_percent,
          disk: snap.disk_percent,
        }));
        setStatsHistory(ordered);
      }
    } catch (err) {
      console.error('Failed to fetch stats history:', err);
    } finally {
      setLoadingStats(false);
    }
  };

  const fetchServicesList = async () => {
    if (!id) return;
    setLoadingServices(true);
    try {
      const data = await api<{ services: any[] }>(`/api/nodes/${id}/services`);
      if (data && data.services) setServices(data.services);
    } catch (err) {
      console.error('Failed to fetch services:', err);
    } finally {
      setLoadingServices(false);
    }
  };

  const fetchContainersList = async () => {
    if (!id) return;
    setLoadingContainers(true);
    try {
      const data = await api<{ containers: any[] }>(`/api/nodes/${id}/containers`);
      if (data && data.containers) setContainers(data.containers);
    } catch (err) {
      console.error('Failed to fetch containers:', err);
    } finally {
      setLoadingContainers(false);
    }
  };

  const fetchNodeLogs = async () => {
    if (!id) return;
    setLoadingLogs(true);
    try {
      const query = `?lines=${logsLimit}${logsService ? `&service=${logsService}` : ''}`;
      const data = await api<{ output: string }>(`/api/nodes/${id}/logs${query}`);
      if (data) setLogs(data.output || 'Aucun log disponible pour cette sélection.');
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      setLogs('Impossible de charger les logs du serveur.');
    } finally {
      setLoadingLogs(false);
    }
  };

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoadingNode(true);
      await fetchNodeDetails();
      setLoadingNode(false);
    };
    init();
  }, [id]);

  // Tab dynamic loading
  useEffect(() => {
    if (activeTab === 'metrics') fetchStatsHistory();
    if (activeTab === 'services') fetchServicesList();
    if (activeTab === 'containers') fetchContainersList();
    if (activeTab === 'logs') fetchNodeLogs();
  }, [activeTab, id]);

  // Polling metrics in background if metrics tab active
  usePolling('detail_metrics_poll', fetchStatsHistory, 15000, activeTab === 'metrics');
  usePolling('detail_logs_poll', fetchNodeLogs, 10000, activeTab === 'logs');

  // Logs Scroll helper
  useEffect(() => {
    if (logsAutoScroll && logsConsoleRef.current) {
      logsConsoleRef.current.scrollTop = logsConsoleRef.current.scrollHeight;
    }
  }, [logs, logsAutoScroll]);

  // Control services restart
  const handleRestartService = async (serviceName: string) => {
    if (!id || !isAdmin) return;
    setRestartingService(serviceName);
    try {
      await api(`/api/nodes/${id}/services/${serviceName}/restart`, { method: 'POST' });
      await fetchServicesList();
    } catch (err) {
      console.error('Service restart error:', err);
    } finally {
      setRestartingService(null);
    }
  };

  // Control containers restart
  const handleRestartContainer = async (containerId: string) => {
    if (!id || !isAdmin) return;
    setRestartingContainer(containerId);
    try {
      await api(`/api/nodes/${id}/containers/${containerId}/restart`, { method: 'POST' });
      await fetchContainersList();
    } catch (err) {
      console.error('Container restart error:', err);
    } finally {
      setRestartingContainer(null);
    }
  };

  if (loadingNode) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-text-3 font-interface text-xs select-none">
        <Spinner size="md" />
        <span>RECHERCHE DES INFORMATIONS DE CONSOLE...</span>
      </div>
    );
  }

  if (!node) {
    return (
      <div className="max-w-xl mx-auto py-20 text-center select-none space-y-4">
        <h1 className="font-serif text-2xl text-text-1">Machine introuvable</h1>
        <p className="text-text-3 text-xs">Le serveur demandé n'existe pas ou sa clé a été révoquée.</p>
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-surface hover:bg-surface-2 border border-border text-xs rounded font-interface font-bold uppercase tracking-wider text-text-2 hover:text-text-1 transition-all cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Retour au Dashboard</span>
        </button>
      </div>
    );
  }

  // Filter lists
  const filteredServices = services.filter((srv) => {
    const matchesSearch = srv.name.toLowerCase().includes(serviceSearch.toLowerCase());
    const matchesStatus =
      serviceFilter === '' ||
      (serviceFilter === 'running' && srv.state === 'running') ||
      (serviceFilter === 'failed' && srv.state === 'failed') ||
      (serviceFilter === 'other' && srv.state !== 'running' && srv.state !== 'failed');
    return matchesSearch && matchesStatus;
  });

  const filteredContainers = containers.filter((cnt) =>
    cnt.name.toLowerCase().includes(containerSearch.toLowerCase()) ||
    cnt.image.toLowerCase().includes(containerSearch.toLowerCase())
  );

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      {/* Back button */}
      <button
        onClick={() => navigate('/')}
        className="inline-flex items-center gap-2 px-3 py-1.5 bg-surface hover:bg-surface-2 border border-border text-[10px] rounded font-interface font-bold uppercase tracking-widest text-text-2 hover:text-text-1 cursor-pointer transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>TABLEAU DE BORD</span>
      </button>

      {/* Header Profile summary */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-xl border border-border bg-surface relative overflow-hidden shadow">
        <div className="flex items-center gap-4 z-10 min-w-0">
          <div className="w-12 h-12 bg-accent-muted border border-accent/20 rounded-xl flex items-center justify-center text-accent">
            <Cpu className="w-6 h-6 text-accent animate-pulse" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <StatusDot state={node.state} />
              <h1 className="font-interface text-lg font-bold text-text-1 truncate">
                {node.name}
              </h1>
              <Badge severity={node.online ? 'ok' : 'offline'} className="text-[8px] px-1 py-0" />
            </div>
            
            <div className="flex items-center gap-3 text-text-3 text-[10px] font-mono mt-1">
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3 opacity-60" /> Enregistré : <TimeAgo timestamp={node.enrolled_at} />
              </span>
              <span>·</span>
              <span>OS : {node.os || 'Linux'} ({node.arch || 'amd64'})</span>
              <span>·</span>
              <span>Hostname : {node.hostname || 'inconnu'}</span>
            </div>
          </div>
        </div>

        {/* Live metric strips */}
        <div className="flex flex-wrap items-center gap-2 shrink-0 z-10">
          {node.online && (
            <MetricPill
              cpu={node.cpu_percent}
              mem={node.memory_percent}
              disk={node.disk_percent}
              uptime={node.uptime_seconds}
              className="text-xs py-1 px-3.5"
            />
          )}
        </div>
      </div>

      {/* Navigation tabs */}
      <div className="border-b border-border font-interface select-none shrink-0 flex overflow-x-auto no-scrollbar gap-4">
        {[
          { id: 'insights', label: 'Analyses IA', count: displayInsights.length },
          { id: 'metrics', label: 'Métriques' },
          { id: 'services', label: `Services (${loadingServices ? '•' : services.length})` },
          { id: 'containers', label: `Docker (${loadingContainers ? '•' : containers.length})` },
          { id: 'logs', label: 'Logs' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`py-2 px-1 text-xs font-bold uppercase tracking-wider border-b-2 cursor-pointer transition-all duration-150 ${
              activeTab === tab.id
                ? 'border-accent text-accent font-extrabold'
                : 'border-transparent text-text-2 hover:text-text-1'
            }`}
          >
            <span className="flex items-center gap-1.5">
              {tab.label}
              {tab.count !== undefined && tab.count > 0 && (
                <span className="px-1.5 py-0.5 rounded-full bg-severity-critical text-white text-[8px] font-mono leading-none">
                  {tab.count}
                </span>
              )}
            </span>
          </button>
        ))}
      </div>

      {/* Tab Panels */}
      <div className="min-h-96">
        {/* Insights Tab */}
        {activeTab === 'insights' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center px-1">
              <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-text-3">
                Insights IA trouvés sur cette machine
              </h3>
              <button
                onClick={refreshInsights}
                disabled={loadingInsights}
                className="p-1 rounded hover:bg-surface-2 text-text-3 hover:text-text-1 cursor-pointer transition-colors"
                title="Rafraîchir les analyses"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingInsights ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {loadingInsights && displayInsights.length === 0 ? (
              <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-3">
                <Spinner size="sm" />
                <span>RÉCUPÉRATION DES RAPPORTS DE DIAGNOSTIC...</span>
              </div>
            ) : displayInsights.length === 0 ? (
              <div className="py-20 border border-dashed border-border rounded-xl bg-surface/30 text-center select-none text-text-3 space-y-2 max-w-lg mx-auto">
                <Sparkles className="w-8 h-8 mx-auto text-severity-ok opacity-45" />
                <h4 className="font-interface text-xs font-bold uppercase tracking-wider text-text-2">Séquence parfaite</h4>
                <p className="text-[10px] leading-relaxed max-w-xs mx-auto text-text-3">
                  Aucun diagnostic ou anomalie sur la machine. Les metrics de performance sont stables.
                </p>
              </div>
            ) : (
              <div className="grid gap-3.5 md:grid-cols-2">
                {displayInsights.map((ins, idx) => {
                  if (ins.type === 'offline') {
                    return (
                      <OfflineInsightCard
                        key={idx}
                        insight={ins}
                        nodeId={id}
                      />
                    );
                  }

                  return (
                    <div
                      key={idx}
                      className="p-5 border border-border rounded-xl bg-surface hover:border-border-strong flex flex-col justify-between h-52 shadow-md transition-all group"
                    >
                      <div className="flex items-center justify-between gap-2 shrink-0">
                        <SeverityTag severity={ins.severity} className="whitespace-nowrap" />
                        <span className="text-[8px] font-extrabold font-interface tracking-widest text-text-3 uppercase whitespace-nowrap">
                          AI REPORT
                        </span>
                      </div>

                      <div className="my-2.5 flex-1 flex flex-col justify-center min-w-0">
                        <InsightText size="sm" className="block text-text-1 leading-snug font-serif !text-[16px] md:!text-[17px] line-clamp-2" title={ins.headline}>
                          {ins.headline}
                        </InsightText>
                        <p className="text-text-3 text-[10px] font-sans mt-1 line-clamp-2 leading-relaxed" title={ins.detail}>
                          {ins.detail}
                        </p>
                      </div>

                      <div className="pt-2 border-t border-border/40 flex items-center justify-between shrink-0">
                        <span title="Assistant IA" className="flex items-center shrink-0">
                          <Sparkles className="w-3.5 h-3.5 text-accent animate-pulse" />
                        </span>
                        <button
                          onClick={() =>
                            openCopilot({
                              trigger: 'diagnostic',
                              insight: ins,
                              node_id: id,
                            })
                          }
                          className="text-[10px] font-extrabold font-interface text-accent hover:underline flex items-center gap-0.5 cursor-pointer"
                        >
                          Diagnostiquer →
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Metrics Tab */}
        {activeTab === 'metrics' && (
          <div className="space-y-6">
            <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-text-3 px-1">
              Historique d'activité (Dernière heure)
            </h3>
            {loadingStats && statsHistory.length === 0 ? (
              <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
                <Spinner size="sm" />
                <span>CHARGEMENT DES HISTOGRAMMES DE SÉCURITÉ...</span>
              </div>
            ) : statsHistory.length === 0 ? (
              <div className="py-20 text-center text-text-3">Aucune métrique historique disponible.</div>
            ) : (
              <div className="grid gap-6 md:grid-cols-3">
                {/* CPU chart */}
                <div className="p-4 border border-border rounded-xl bg-surface flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-text-1 font-interface font-bold text-xs uppercase tracking-wide">
                    <Cpu className="w-4 h-4 text-accent" /> Charge Processeur (%)
                  </div>
                  <div className="h-48 w-full mt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={statsHistory} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                        <XAxis dataKey="time" stroke="var(--text-2)" fontSize={8} tickLine={false} />
                        <YAxis stroke="var(--text-2)" fontSize={8} tickLine={false} domain={[0, 100]} />
                        <Tooltip contentStyle={{ background: 'var(--surface-2)', borderColor: 'var(--border-strong)', fontSize: '10px' }} />
                        <Line type="monotone" dataKey="cpu" stroke="var(--accent)" strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Memory chart */}
                <div className="p-4 border border-border rounded-xl bg-surface flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-text-1 font-interface font-bold text-xs uppercase tracking-wide">
                    <Database className="w-4 h-4 text-severity-warning" /> Charge Mémoire (%)
                  </div>
                  <div className="h-48 w-full mt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={statsHistory} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                        <XAxis dataKey="time" stroke="var(--text-2)" fontSize={8} tickLine={false} />
                        <YAxis stroke="var(--text-2)" fontSize={8} tickLine={false} domain={[0, 100]} />
                        <Tooltip contentStyle={{ background: 'var(--surface-2)', borderColor: 'var(--border-strong)', fontSize: '10px' }} />
                        <Line type="monotone" dataKey="ram" stroke="var(--severity-warning)" strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Disk chart */}
                <div className="p-4 border border-border rounded-xl bg-surface flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-text-1 font-interface font-bold text-xs uppercase tracking-wide">
                    <Layers className="w-4 h-4 text-severity-info" /> Stockage Disque (%)
                  </div>
                  <div className="h-48 w-full mt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={statsHistory} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                        <XAxis dataKey="time" stroke="var(--text-2)" fontSize={8} tickLine={false} />
                        <YAxis stroke="var(--text-2)" fontSize={8} tickLine={false} domain={[0, 100]} />
                        <Tooltip contentStyle={{ background: 'var(--surface-2)', borderColor: 'var(--border-strong)', fontSize: '10px' }} />
                        <Line type="monotone" dataKey="disk" stroke="var(--severity-info)" strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Services Tab */}
        {activeTab === 'services' && (
          <div className="space-y-4">
            {/* Filter toolbar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-3" />
                <input
                  type="text"
                  placeholder="Rechercher un service systemd..."
                  value={serviceSearch}
                  onChange={(e) => setServiceSearch(e.target.value)}
                  className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded pl-10 pr-3.5 py-1.5 text-xs text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
                />
              </div>

              <div className="flex items-center gap-2 font-interface text-xs">
                <select
                  value={serviceFilter}
                  onChange={(e) => setServiceFilter(e.target.value)}
                  className="bg-surface-2 border border-border rounded px-3 py-1.5 focus:outline-none text-text-2 font-semibold"
                >
                  <option value="">Tous les états</option>
                  <option value="running">En cours d'exécution</option>
                  <option value="failed">En panne (failed)</option>
                  <option value="other">Autre</option>
                </select>
                <button
                  onClick={fetchServicesList}
                  disabled={loadingServices}
                  className="p-1.5 rounded hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer transition-colors"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingServices ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {loadingServices && services.length === 0 ? (
              <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
                <Spinner size="sm" />
                <span>CONSULTATION DE LA LISTE SYSTEMD...</span>
              </div>
            ) : filteredServices.length === 0 ? (
              <div className="py-12 text-center text-text-3 text-xs bg-surface/20 border border-border rounded-lg">
                Aucun service ne correspond aux critères.
              </div>
            ) : (
              <div className="border border-border rounded-xl bg-surface overflow-hidden shadow">
                <table className="w-full text-left border-collapse text-xs font-sans">
                  <thead>
                    <tr className="bg-surface-2/45 border-b border-border text-[9px] font-extrabold font-interface tracking-widest text-text-3 uppercase">
                      <th className="px-5 py-3">Nom du Service</th>
                      <th className="px-5 py-3">État actuel</th>
                      <th className="px-5 py-3">Statut technique</th>
                      {isAdminOrOperator && <th className="px-5 py-3 text-right">Contrôle</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {filteredServices.map((srv) => (
                      <tr key={srv.name} className="hover:bg-surface-2/20">
                        <td className="px-5 py-3.5 font-mono text-[11.5px] text-text-1 font-bold truncate max-w-[280px]" title={srv.name}>
                          {srv.name}
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold border uppercase tracking-wider font-interface ${
                            srv.state === 'running' 
                              ? 'bg-severity-ok/10 text-severity-ok border-severity-ok/20'
                              : srv.state === 'failed'
                              ? 'bg-severity-critical/10 text-severity-critical border-severity-critical/20 animate-pulse'
                              : 'bg-text-3/15 text-text-2 border-border'
                          }`}>
                            {srv.state}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 font-mono text-[10px] text-text-3 truncate max-w-[200px]" title={srv.status}>
                          {srv.status || 'aucun détail'}
                        </td>
                        {isAdminOrOperator && (
                          <td className="px-5 py-3.5 text-right font-interface">
                            <button
                              onClick={() => handleRestartService(srv.name)}
                              disabled={restartingService !== null || !isAdmin}
                              className="px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent hover:bg-accent/5 rounded cursor-pointer disabled:opacity-50 transition-all duration-150"
                              title={isAdmin ? "Redémarrer le service" : "Droits administrateur requis"}
                            >
                              {restartingService === srv.name ? 'Redémarrage...' : 'Restart'}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Containers Tab */}
        {activeTab === 'containers' && (
          <div className="space-y-4">
            {/* Filter toolbar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-3" />
                <input
                  type="text"
                  placeholder="Rechercher par nom ou image Docker..."
                  value={containerSearch}
                  onChange={(e) => setContainerSearch(e.target.value)}
                  className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded pl-10 pr-3.5 py-1.5 text-xs text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
                />
              </div>

              <button
                onClick={fetchContainersList}
                disabled={loadingContainers}
                className="p-1.5 rounded hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer transition-colors ml-auto font-interface"
              >
                <RefreshCw className={`w-4 h-4 ${loadingContainers ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {loadingContainers && containers.length === 0 ? (
              <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
                <Spinner size="sm" />
                <span>DIAGNOSTIC DE L'SOCKET DOCKER...</span>
              </div>
            ) : filteredContainers.length === 0 ? (
              <div className="py-12 text-center text-text-3 text-xs bg-surface/20 border border-border rounded-lg">
                Aucun conteneur docker détecté ou actif.
              </div>
            ) : (
              <div className="border border-border rounded-xl bg-surface overflow-hidden shadow">
                <table className="w-full text-left border-collapse text-xs font-sans">
                  <thead>
                    <tr className="bg-surface-2/45 border-b border-border text-[9px] font-extrabold font-interface tracking-widest text-text-3 uppercase">
                      <th className="px-5 py-3">Conteneur</th>
                      <th className="px-5 py-3">Image source</th>
                      <th className="px-5 py-3">Statut Docker</th>
                      <th className="px-5 py-3">Routage Ports</th>
                      {isAdminOrOperator && <th className="px-5 py-3 text-right">Contrôle</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {filteredContainers.map((cnt) => (
                      <tr key={cnt.id} className="hover:bg-surface-2/20">
                        <td className="px-5 py-3.5 font-interface text-xs text-text-1 font-bold truncate max-w-[160px]" title={cnt.name}>
                          {cnt.name}
                        </td>
                        <td className="px-5 py-3.5 font-mono text-[10px] text-text-3 truncate max-w-[200px]" title={cnt.image}>
                          {cnt.image}
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold border uppercase tracking-wider font-interface ${
                            cnt.state.toLowerCase() === 'running'
                              ? 'bg-severity-ok/10 text-severity-ok border-severity-ok/20'
                              : 'bg-text-3/15 text-text-2 border-border'
                          }`}>
                            {cnt.state}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 font-mono text-[9.5px] text-text-3 truncate max-w-[160px]" title={Array.isArray(cnt.ports) ? cnt.ports.join(', ') : String(cnt.ports || '')}>
                          {Array.isArray(cnt.ports) ? cnt.ports.join(', ') : (cnt.ports || 'aucun')}
                        </td>
                        {isAdminOrOperator && (
                          <td className="px-5 py-3.5 text-right font-interface">
                            <button
                              onClick={() => handleRestartContainer(cnt.id)}
                              disabled={restartingContainer !== null || !isAdmin}
                              className="px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent hover:bg-accent/5 rounded cursor-pointer disabled:opacity-50 transition-all duration-150"
                              title={isAdmin ? "Redémarrer le conteneur" : "Droits administrateur requis"}
                            >
                              {restartingContainer === cnt.id ? 'Redémarrage...' : 'Restart'}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Logs Tab */}
        {activeTab === 'logs' && (
          <div className="space-y-4">
            {/* Logs configuration bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg font-interface text-xs select-none">
              <div className="flex flex-wrap items-center gap-3">
                {/* Service filtering */}
                <div className="flex items-center gap-1.5">
                  <span className="text-text-3 font-semibold uppercase tracking-wider text-[10px]">Cible :</span>
                  <select
                    value={logsService}
                    onChange={(e) => setLogsService(e.target.value)}
                    className="bg-surface-2 border border-border rounded px-2.5 py-1 focus:outline-none text-text-2 font-semibold"
                  >
                    <option value="">Système global (journalctl)</option>
                    {services.map((srv) => (
                      <option key={srv.name} value={srv.name}>{srv.name}</option>
                    ))}
                  </select>
                </div>

                {/* Lines limits */}
                <div className="flex items-center gap-1.5">
                  <span className="text-text-3 font-semibold uppercase tracking-wider text-[10px]">Lignes :</span>
                  <select
                    value={logsLimit}
                    onChange={(e) => setLogsLimit(Number(e.target.value))}
                    className="bg-surface-2 border border-border rounded px-2.5 py-1 focus:outline-none text-text-2 font-semibold"
                  >
                    <option value="50">50 lignes</option>
                    <option value="100">100 lignes</option>
                    <option value="250">250 lignes</option>
                  </select>
                </div>

                {/* Auto Scroll */}
                <label className="flex items-center gap-1.5 text-text-2 cursor-pointer font-semibold">
                  <input
                    type="checkbox"
                    checked={logsAutoScroll}
                    onChange={(e) => setLogsAutoScroll(e.target.checked)}
                    className="rounded bg-surface-2 border-border accent-accent"
                  />
                  <span>Défilement automatique</span>
                </label>
              </div>

              <button
                onClick={fetchNodeLogs}
                disabled={loadingLogs}
                className="p-1.5 rounded hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer transition-colors ml-auto"
              >
                <RefreshCw className={`w-4 h-4 ${loadingLogs ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Logs console window */}
            <div className="relative">
              {loadingLogs && (
                <div className="absolute inset-0 bg-surface/50 backdrop-blur-xs flex items-center justify-center z-10 rounded-lg">
                  <Spinner size="sm" />
                </div>
              )}
              <div
                ref={logsConsoleRef}
                className="font-mono text-[10.5px] leading-relaxed p-5 bg-black text-text-2 border border-border rounded-lg h-[460px] overflow-y-auto whitespace-pre-wrap select-text scrollbar-thin shadow-inner"
              >
                {logs || 'Aucune ligne de journalisation n\'a pu être collectée.'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
