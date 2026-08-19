export type NodeDetailTabId =
  | 'insights'
  | 'metrics'
  | 'services'
  | 'containers'
  | 'logs'
  | 'disk'
  | 'settings';

export interface ServiceRecord {
  name: string;
  state: string;
  status?: string;
  [key: string]: unknown;
}

export interface ContainerRecord {
  id: string;
  name: string;
  image: string;
  state: string;
  ports?: string[] | string;
  [key: string]: unknown;
}

export interface DiskMount {
  mount_point: string;
  fs_type: string;
  device: string;
  total_bytes: number;
  used_bytes: number;
  percent: number;
  days_left?: number;
  growth_gb_per_day?: number;
}

export interface TopProcess {
  pid: number;
  name: string;
  cpu_percent: number;
  mem_rss_kb?: number;
  state?: string;
  [key: string]: unknown;
}

export interface StatsPoint {
  collected_at?: number;
  time: string;
  cpu: number;
  ram: number;
  disk: number;
  disks?: DiskMount[];
  top_processes?: TopProcess[];
}

export interface AlertRecord {
  id: string;
  node_id: string;
  alert_name: string;
  severity: 'info' | 'warning' | 'critical';
  status: 'firing' | 'resolved';
  message: string;
  metric_value?: number | null;
  threshold?: number | null;
  details?: {
    top_process?: TopProcess;
    top_processes?: TopProcess[];
    [key: string]: unknown;
  } | null;
  created_at: number;
  resolved_at?: number | null;
  updated_at?: number | null;
}

export interface MetricBaseline {
  mean: number;
  std: number;
  p75: number;
  p90: number;
  p99: number;
  absolute_warning: number;
  absolute_critical: number;
}

export interface NodeBaseline {
  node_id: string;
  data_window_hours: number;
  is_limited: boolean;
  metrics: {
    cpu: MetricBaseline;
    ram: MetricBaseline;
    disk: MetricBaseline;
  };
}

export type Severity = 'ok' | 'warning' | 'critical' | 'offline' | 'info';

export interface InsightRecord {
  type: string;
  severity: Severity;
  icon: string;
  headline: string;
  detail: string;
  confidence?: 'none' | 'low' | 'medium' | 'high';
  raw?: Record<string, unknown>;
}

export interface TypeReadiness {
  ready: boolean;
  hours: number;
  required: number;
}

export interface PerTypeReadiness {
  cpu: TypeReadiness;
  ram: TypeReadiness;
  disk: TypeReadiness;
  profile: TypeReadiness;
}

/** Metadata returned alongside insights from GET /{node_id}/insights */
export interface InsightsMeta {
  data_window_hours: number;
  observation_ready: boolean;
  profile_confidence: 'none' | 'low' | 'medium' | 'high';
  next_profile_refresh_at: string | null;
  profile_generated_at: string | null;
  per_type_readiness?: PerTypeReadiness;
}

export interface InsightsResponse {
  node_id: string;
  generated_at: string;
  insights: InsightRecord[];
  data_window_hours: number;
  observation_ready: boolean;
  profile_confidence: 'none' | 'low' | 'medium' | 'high';
  next_profile_refresh_at: string | null;
  profile_generated_at: string | null;
  per_type_readiness?: PerTypeReadiness;
}

export interface NodeRecord {
  id: string;
  name: string;
  hostname: string | null;
  machine_id: string | null;
  os: string | null;
  arch: string | null;
  state: string;
  online: boolean;
  last_heartbeat: number | null;
  enrolled_at: number | null;
  created_at: number;
  updated_at: number;
  group: string | null;
  disabled: boolean;
  enrolled_recently: boolean;
  cpu_percent?: number;
  memory_percent?: number;
  disk_percent?: number;
  uptime_seconds?: number;
  version?: string;
  worker_version?: string;
  cached_disks_json: string | null;
}

export interface LogEntryRecord {
  timestamp: number;
  time_str: string;
  level: 'error' | 'warn' | 'info' | 'debug' | string;
  unit: string;
  message: string;
  raw?: Record<string, unknown>;
}

export interface LogSourceItemRecord {
  id: string;
  name: string;
  category: 'files' | 'services' | 'docker' | string;
  path?: string;
  unit?: string;
  size_bytes?: number;
  mtime?: number;
  error_count: number;
  status?: string;
}

export interface HistogramBucketRecord {
  hour: string;
  timestamp: number;
  info: number;
  warn: number;
  error: number;
  total: number;
}

export interface LogHistogramRecord {
  node_id: string;
  buckets: HistogramBucketRecord[];
  total_errors: number;
  total_warnings: number;
  total_lines: number;
}
