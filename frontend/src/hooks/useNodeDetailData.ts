import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../hooks/useApi';
import { useNodeInsights } from '../hooks/useNodeInsights';
import { t } from '../i18n';
import type { TimeRangePreset } from '../components/node-detail/MetricsOverview';
import type {
  ContainerRecord,
  InsightRecord,
  InsightsMeta,
  NodeRecord,
  ServiceRecord,
  StatsPoint,
  DiskMount,
  LogEntryRecord,
  LogSourceItemRecord,
  LogHistogramRecord,
} from '../components/node-detail/types';

const METRICS_RANGE_KEY = 'vigile_metrics_range';
const RANGE_DURATIONS: Record<string, number> = {
  '1h': 3600,
  '6h': 21600,
  '12h': 43200,
  '24h': 86400,
  '7d': 604800,
  '30d': 2592000,
};

interface SavedMetricsRange {
  preset: TimeRangePreset;
  custom?: { start: number; end: number };
}

function loadSavedMetricsRange(): SavedMetricsRange {
  try {
    const raw = localStorage.getItem(METRICS_RANGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as SavedMetricsRange;
      if (parsed && typeof parsed.preset === 'string') {
        return { preset: parsed.preset, custom: parsed.custom };
      }
    }
  } catch {
    // corrupted storage -> fall back to default
  }
  return { preset: '1h' };
}

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
  logEntries: LogEntryRecord[];
  loadingLogs: boolean;
  logsService: string;
  setLogsService: (v: string) => void;
  logsPath: string;
  setLogsPath: (v: string) => void;
  logsLimit: number;
  setLogsLimit: (v: number) => void;
  logsSince: string;
  setLogsSince: (v: string) => void;
  logsUntil: string;
  setLogsUntil: (v: string) => void;
  logsAutoScroll: boolean;
  setLogsAutoScroll: (v: boolean) => void;
  fetchNodeLogs: (skipToast?: boolean) => Promise<void>;
  logSources: LogSourceItemRecord[];
  loadingLogSources: boolean;
  fetchLogSources: () => Promise<void>;
  logHistogram: LogHistogramRecord | null;
  loadingHistogram: boolean;
  fetchLogHistogram: () => Promise<void>;
  selectedBucketHour: string | null;
  setSelectedBucketHour: (v: string | null) => void;
  restartingService: string | null;
  setRestartingService: (v: string | null) => void;
  restartingContainer: string | null;
  setRestartingContainer: (v: string | null) => void;
  insightsMeta: InsightsMeta | null;
  nodeAlerts: AlertRecord[];
  nodeBaseline: NodeBaseline | null;
  fetchNodeBaseline: () => Promise<void>;
  timeRange: TimeRangePreset;
  setTimeRange: (preset: TimeRangePreset, startSec?: number, endSec?: number) => void;
  refreshStatsForRange: () => Promise<void>;
}

export function useNodeDetailData(nodeId: string | undefined, activePlugins: string[] | null): NodeDetailData {
  const { insights, loading: loadingInsights, refresh: refreshInsights, meta: insightsMeta } = useNodeInsights(nodeId || null);

  const [node, setNode] = useState<NodeRecord | null>(null);
  const [loadingNode, setLoadingNode] = useState(true);

  const [statsHistory, setStatsHistory] = useState<StatsPoint[]>([]);
  const [loadingStats, setLoadingStats] = useState(false);

  const [services, setServices] = useState<ServiceRecord[]>([]);
  const [loadingServices, setLoadingServices] = useState(false);

  const [containers, setContainers] = useState<ContainerRecord[]>([]);
  const [loadingContainers, setLoadingContainers] = useState(false);

  const [logs, setLogs] = useState<string>('');
  const [logEntries, setLogEntries] = useState<LogEntryRecord[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logsService, setLogsService] = useState<string>('');
  const [logsPath, setLogsPath] = useState<string>('');
  const [logsLimit, setLogsLimit] = useState<number>(100);
  const [logsSince, setLogsSince] = useState<string>('');
  const [logsUntil, setLogsUntil] = useState<string>('');
  const [logsAutoScroll, setLogsAutoScroll] = useState(true);

  const [logSources, setLogSources] = useState<LogSourceItemRecord[]>([]);
  const [loadingLogSources, setLoadingLogSources] = useState(false);

  const [logHistogram, setLogHistogram] = useState<LogHistogramRecord | null>(null);
  const [loadingHistogram, setLoadingHistogram] = useState(false);
  const [selectedBucketHour, setSelectedBucketHour] = useState<string | null>(null);

  const [restartingService, setRestartingService] = useState<string | null>(null);
  const [restartingContainer, setRestartingContainer] = useState<string | null>(null);

  const [timeRange, setTimeRangeState] = useState<TimeRangePreset>(() => loadSavedMetricsRange().preset);
  const rangeRef = useRef<SavedMetricsRange>(loadSavedMetricsRange());

  const fetchNodeDetails = useCallback(async () => {
    if (!nodeId) return;
    try {
      const data = await api<NodeRecord>(`/api/nodes/${nodeId}`);
      if (data) setNode(data);
    } catch (err) {
      console.error('Failed to fetch node:', err);
    }
  }, [nodeId]);

  const [nodeAlerts, setNodeAlerts] = useState<AlertRecord[]>([]);
  const [nodeBaseline, setNodeBaseline] = useState<NodeBaseline | null>(null);

  const fetchNodeAlerts = useCallback(async (startSec?: number, endSec?: number) => {
    if (!nodeId) return;
    try {
      let url = `/api/nodes/${nodeId}/alerts`;
      const params = new URLSearchParams();
      if (startSec) params.append('start', startSec.toString());
      if (endSec) params.append('end', endSec.toString());
      if (params.toString()) url += `?${params.toString()}`;

      const res = await api<{ alerts: AlertRecord[] }>(url, { skipToast: true });
      if (res && res.alerts) setNodeAlerts(res.alerts);
    } catch (err) {
      console.error('Failed to fetch node alerts:', err);
    }
  }, [nodeId]);

  const fetchNodeBaseline = useCallback(async () => {
    if (!nodeId) return;
    try {
      const res = await api<NodeBaseline>(`/api/nodes/${nodeId}/baseline`, { skipToast: true });
      if (res && res.metrics) setNodeBaseline(res);
    } catch (err) {
      console.error('Failed to fetch node baseline:', err);
    }
  }, [nodeId]);

  const fetchStatsHistory = useCallback(async (skipToast = false, startSec?: number, endSec?: number) => {
    if (!nodeId) return;
    setLoadingStats(true);
    try {
      let query = `?limit=1440`;
      if (startSec && endSec) {
        query += `&start=${startSec}&end=${endSec}`;
      }
      const data = await api<{ snapshots: StatsSnapshot[] }>(`/api/nodes/${nodeId}/stats${query}`, { skipToast });
      if (data && data.snapshots) {
        const isLongRange = startSec && endSec && (endSec - startSec) > 86400;
        const ordered = [...data.snapshots].reverse().map((snap) => ({
          collected_at: snap.collected_at,
          time: isLongRange
            ? new Date(snap.collected_at * 1000).toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
            : new Date(snap.collected_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          cpu: snap.cpu_percent,
          ram: snap.mem_percent,
          disk: snap.disk_percent,
          disks: snap.disks,
        }));
        setStatsHistory(ordered);
      }
      void fetchNodeAlerts(startSec, endSec);
    } catch (err) {
      console.error('Failed to fetch stats history:', err);
    } finally {
      setLoadingStats(false);
    }
  }, [nodeId, fetchNodeAlerts]);

  const fetchStatsForRange = useCallback((range: SavedMetricsRange) => {
    if (range.preset === 'custom' && range.custom) {
      return fetchStatsHistory(true, range.custom.start, range.custom.end);
    }
    const now = Math.floor(Date.now() / 1000);
    const duration = RANGE_DURATIONS[range.preset] ?? 3600;
    return fetchStatsHistory(true, now - duration, now);
  }, [fetchStatsHistory]);

  const setTimeRange = useCallback((preset: TimeRangePreset, startSec?: number, endSec?: number) => {
    const custom = preset === 'custom' && startSec && endSec ? { start: startSec, end: endSec } : undefined;
    const next: SavedMetricsRange = { preset, custom };
    rangeRef.current = next;
    setTimeRangeState(preset);
    try {
      localStorage.setItem(METRICS_RANGE_KEY, JSON.stringify(next));
    } catch {
      // storage unavailable (private mode) -> selection kept for the session only
    }
    void fetchStatsForRange(next);
  }, [fetchStatsForRange]);

  const refreshStatsForRange = useCallback(() => fetchStatsForRange(rangeRef.current), [fetchStatsForRange]);

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
      const params = new URLSearchParams();
      params.set('lines', String(logsLimit));
      if (logsService) params.set('service', logsService);
      if (logsPath) params.set('path', logsPath);
      if (logsSince) params.set('since', logsSince);
      if (logsUntil) params.set('until', logsUntil);

      const data = await api<{ output: string; entries?: LogEntryRecord[]; error?: string }>(
        `/api/nodes/${nodeId}/logs?${params.toString()}`,
        { skipToast }
      );
      if (data) {
        if (data.error) {
          setLogs(`Error: ${data.error}`);
          setLogEntries([]);
        } else {
          setLogs(data.output || t('node_detail.logs_selection_empty'));
          setLogEntries(data.entries || []);
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
  }, [nodeId, logsLimit, logsService, logsPath, logsSince, logsUntil]);

  const fetchLogSources = useCallback(async () => {
    if (!nodeId) return;
    setLoadingLogSources(true);
    try {
      const data = await api<{ sources: LogSourceItemRecord[] }>(`/api/nodes/${nodeId}/log-sources`, { timeoutMs: 20000 });
      if (data && data.sources) {
        setLogSources(data.sources);
      }
    } catch (err) {
      console.error('Failed to fetch log sources:', err);
    } finally {
      setLoadingLogSources(false);
    }
  }, [nodeId]);

  const fetchLogHistogram = useCallback(async () => {
    if (!nodeId) return;
    setLoadingHistogram(true);
    try {
      const data = await api<LogHistogramRecord>(`/api/nodes/${nodeId}/logs/histogram`, { timeoutMs: 20000 });
      if (data) {
        setLogHistogram(data);
      }
    } catch (err) {
      console.error('Failed to fetch log histogram:', err);
    } finally {
      setLoadingHistogram(false);
    }
  }, [nodeId]);

  const servicesEnabled = activePlugins !== null && activePlugins.includes('systemd');
  const containersEnabled = activePlugins !== null && activePlugins.includes('docker');

  useEffect(() => {
    const init = async () => {
      setLoadingNode(true);
      await fetchNodeDetails();
      setLoadingNode(false);
      if (servicesEnabled) fetchServicesList();
      if (containersEnabled) fetchContainersList();
      fetchLogSources();
      fetchLogHistogram();
    };
    init();
  }, [fetchNodeDetails, fetchServicesList, fetchContainersList, fetchLogSources, fetchLogHistogram, servicesEnabled, containersEnabled]);

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
    logEntries,
    loadingLogs,
    logsService,
    setLogsService,
    logsPath,
    setLogsPath,
    logsLimit,
    setLogsLimit,
    logsSince,
    setLogsSince,
    logsUntil,
    setLogsUntil,
    logsAutoScroll,
    setLogsAutoScroll,
    fetchNodeLogs,
    logSources,
    loadingLogSources,
    fetchLogSources,
    logHistogram,
    loadingHistogram,
    fetchLogHistogram,
    selectedBucketHour,
    setSelectedBucketHour,
    restartingService,
    setRestartingService,
    restartingContainer,
    setRestartingContainer,
    insightsMeta,
    nodeAlerts,
    nodeBaseline,
    fetchNodeBaseline,
    timeRange,
    setTimeRange,
    refreshStatsForRange,
  };
}
