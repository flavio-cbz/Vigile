import { useCallback, useEffect, useState } from 'react';
import { api } from '../hooks/useApi';
import { useNodeInsights } from '../hooks/useNodeInsights';
import { t } from '../i18n';
import type {
  ContainerRecord,
  InsightRecord,
  NodeRecord,
  ServiceRecord,
  StatsPoint,
  DiskMount,
} from '../components/node-detail/types';

interface StatsSnapshot {
  collected_at: number;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
  disks?: DiskMount[];
}

export interface NodeDetailData {
  node: NodeRecord | null;
  loadingNode: boolean;
  insights: InsightRecord[];
  loadingInsights: boolean;
  refreshInsights: () => void;
  displayInsights: InsightRecord[];
  statsHistory: StatsPoint[];
  loadingStats: boolean;
  fetchStatsHistory: (skipToast?: boolean) => Promise<void>;
  services: ServiceRecord[];
  loadingServices: boolean;
  fetchServicesList: () => Promise<void>;
  containers: ContainerRecord[];
  loadingContainers: boolean;
  fetchContainersList: () => Promise<void>;
  logs: string;
  loadingLogs: boolean;
  logsService: string;
  setLogsService: (v: string) => void;
  logsLimit: number;
  setLogsLimit: (v: number) => void;
  logsAutoScroll: boolean;
  setLogsAutoScroll: (v: boolean) => void;
  fetchNodeLogs: (skipToast?: boolean) => Promise<void>;
  restartingService: string | null;
  setRestartingService: (v: string | null) => void;
  restartingContainer: string | null;
  setRestartingContainer: (v: string | null) => void;
}

export function useNodeDetailData(nodeId: string | undefined): NodeDetailData {
  const { insights, loading: loadingInsights, refresh: refreshInsights } = useNodeInsights(nodeId || null);

  const [node, setNode] = useState<NodeRecord | null>(null);
  const [loadingNode, setLoadingNode] = useState(true);

  const [statsHistory, setStatsHistory] = useState<StatsPoint[]>([]);
  const [loadingStats, setLoadingStats] = useState(false);

  const [services, setServices] = useState<ServiceRecord[]>([]);
  const [loadingServices, setLoadingServices] = useState(false);

  const [containers, setContainers] = useState<ContainerRecord[]>([]);
  const [loadingContainers, setLoadingContainers] = useState(false);

  const [logs, setLogs] = useState<string>('');
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logsService, setLogsService] = useState<string>('');
  const [logsLimit, setLogsLimit] = useState<number>(100);
  const [logsAutoScroll, setLogsAutoScroll] = useState(true);

  const [restartingService, setRestartingService] = useState<string | null>(null);
  const [restartingContainer, setRestartingContainer] = useState<string | null>(null);

  const fetchNodeDetails = useCallback(async () => {
    if (!nodeId) return;
    try {
      const data = await api<NodeRecord>(`/api/nodes/${nodeId}`);
      if (data) setNode(data);
    } catch (err) {
      console.error('Failed to fetch node:', err);
    }
  }, [nodeId]);

  const fetchStatsHistory = useCallback(async (skipToast = false) => {
    if (!nodeId) return;
    setLoadingStats(true);
    try {
      const data = await api<{ snapshots: StatsSnapshot[] }>(`/api/nodes/${nodeId}/stats?limit=60`, { skipToast });
      if (data && data.snapshots) {
        const ordered = [...data.snapshots].reverse().map((snap) => ({
          time: new Date(snap.collected_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          cpu: snap.cpu_percent,
          ram: snap.mem_percent,
          disk: snap.disk_percent,
          disks: snap.disks,
        }));
        setStatsHistory(ordered);
      }
    } catch (err) {
      console.error('Failed to fetch stats history:', err);
    } finally {
      setLoadingStats(false);
    }
  }, [nodeId]);

  const fetchServicesList = useCallback(async () => {
    if (!nodeId) return;
    setLoadingServices(true);
    try {
      const data = await api<{ services: ServiceRecord[] }>(`/api/nodes/${nodeId}/services`, { timeoutMs: 30000 });
      if (data && data.services) setServices(data.services);
    } catch (err) {
      console.error('Failed to fetch services:', err);
    } finally {
      setLoadingServices(false);
    }
  }, [nodeId]);

  const fetchContainersList = useCallback(async () => {
    if (!nodeId) return;
    setLoadingContainers(true);
    try {
      const data = await api<{ containers: ContainerRecord[] }>(`/api/nodes/${nodeId}/containers`, { timeoutMs: 30000 });
      if (data && data.containers) setContainers(data.containers);
    } catch (err) {
      console.error('Failed to fetch containers:', err);
    } finally {
      setLoadingContainers(false);
    }
  }, [nodeId]);

  const fetchNodeLogs = useCallback(async (skipToast = false) => {
    if (!nodeId) return;
    setLoadingLogs(true);
    try {
      const query = `?lines=${logsLimit}${logsService ? `&service=${logsService}` : ''}`;
      const data = await api<{ output: string; error?: string }>(`/api/nodes/${nodeId}/logs${query}`, { skipToast });
      if (data) {
        if (data.error) {
          setLogs(`Error: ${data.error}`);
        } else {
          setLogs(data.output || t('node_detail.logs_selection_empty'));
        }
      }
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      if (!skipToast) {
        setLogs(t('node_detail.logs_load_error'));
      }
    } finally {
      setLoadingLogs(false);
    }
  }, [nodeId, logsLimit, logsService]);

  useEffect(() => {
    const init = async () => {
      setLoadingNode(true);
      await fetchNodeDetails();
      setLoadingNode(false);
      fetchServicesList();
      fetchContainersList();
    };
    init();
  }, [fetchNodeDetails, fetchServicesList, fetchContainersList]);

  const displayInsights: InsightRecord[] = [...insights];
  if (node && !node.online) {
    const hbTime = node.last_heartbeat;
    const hbLabel = hbTime
      ? new Date(hbTime < 9999999999 ? hbTime * 1000 : hbTime).toLocaleString('fr-FR')
      : null;
    displayInsights.unshift({
      type: 'offline',
      severity: 'offline',
      icon: '📡',
      headline: hbTime
        ? t('dash.insight_offline_headline', { time: hbLabel ?? '' })
        : t('dash.insight_offline_headline_no_hb'),
      detail: hbTime
        ? t('dash.insight_offline_detail', { time: hbLabel ?? '' })
        : t('dash.insight_offline_detail_no_hb'),
      raw: { last_heartbeat: hbTime },
    });
  }

  return {
    node,
    loadingNode,
    insights,
    loadingInsights,
    refreshInsights,
    displayInsights,
    statsHistory,
    loadingStats,
    fetchStatsHistory,
    services,
    loadingServices,
    fetchServicesList,
    containers,
    loadingContainers,
    fetchContainersList,
    logs,
    loadingLogs,
    logsService,
    setLogsService,
    logsLimit,
    setLogsLimit,
    logsAutoScroll,
    setLogsAutoScroll,
    fetchNodeLogs,
    restartingService,
    setRestartingService,
    restartingContainer,
    setRestartingContainer,
  };
}
