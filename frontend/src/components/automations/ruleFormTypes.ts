export type TriggerType = 'metric_threshold' | 'node_state';
export type ActionType = 'send_intent' | 'call_webhook' | 'log_message';
export type ConditionType = 'always' | 'time_window';

export interface FormAction {
  type: ActionType;
  action?: string;
  params?: Record<string, string>;
  url?: string;
  body_template?: string;
  headers?: Record<string, string>;
  message?: string;
}

export interface FormCondition {
  type: ConditionType;
  window?: string;
}

export const METRICS = [
  { value: 'cpu_percent', label: 'CPU %' },
  { value: 'cpu_load_1m', label: 'Load 1m' },
  { value: 'cpu_load_5m', label: 'Load 5m' },
  { value: 'cpu_load_15m', label: 'Load 15m' },
  { value: 'mem_percent', label: 'Mémoire %' },
  { value: 'disk_percent', label: 'Disque %' },
  { value: 'uptime_seconds', label: 'Uptime (secondes)' },
  { value: 'processes', label: 'Processus' },
];

export const OPERATORS = [
  { value: 'gt', label: '> (supérieur)' },
  { value: 'gte', label: '≥ (supérieur ou égal)' },
  { value: 'lt', label: '< (inférieur)' },
  { value: 'lte', label: '≤ (inférieur ou égal)' },
  { value: 'eq', label: '= (égal)' },
];

export const NODE_STATES = ['CONNECTED', 'LOST', 'STALE', 'RECONNECTING'];

export const INTENT_ACTIONS = [
  'LIST_SERVICES', 'STATUS_SERVICE', 'RESTART_SERVICE',
  'LIST_CONTAINERS', 'RESTART_CONTAINER', 'GET_STATS', 'READ_LOGS',
];
