export type NodeDetailTabId =
  | 'insights'
  | 'metrics'
  | 'services'
  | 'containers'
  | 'logs'
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
}

export interface StatsPoint {
  time: string;
  cpu: number;
  ram: number;
  disk: number;
  disks?: DiskMount[];
}

export type Severity = 'ok' | 'warning' | 'critical' | 'offline' | 'info';

export interface InsightRecord {
  type: string;
  severity: Severity;
  icon: string;
  headline: string;
  detail: string;
  raw?: Record<string, unknown>;
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
}
