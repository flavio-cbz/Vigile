import type React from 'react';

export interface AutomationRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  trigger_type: 'metric_threshold' | 'node_state';
  trigger_config: Record<string, unknown>;
  conditions: Record<string, unknown>[];
  actions: Record<string, unknown>[];
  target_node_id: string | null;
  target_group: string | null;
  cooldown_seconds: number;
  created_by: string;
  created_at: number;
  updated_at: number;
  total_executions: number;
  last_triggered_at: number | null;
}

const METRIC_LABELS: Record<string, string> = {
  cpu_percent: 'CPU %',
  cpu_load_1m: 'Load 1m',
  cpu_load_5m: 'Load 5m',
  cpu_load_15m: 'Load 15m',
  mem_percent: 'Mémoire %',
  disk_percent: 'Disque %',
  uptime_seconds: 'Uptime (s)',
  processes: 'Processus',
};

const OPERATOR_SYMBOLS: Record<string, string> = {
  gt: '>',
  lt: '<',
  gte: '≥',
  lte: '≤',
  eq: '=',
};

export function formatTrigger(rule: AutomationRule): string {
  if (rule.trigger_type === 'metric_threshold') {
    const cfg = rule.trigger_config;
    const metric = METRIC_LABELS[cfg.metric as string] ?? String(cfg.metric);
    const op = OPERATOR_SYMBOLS[cfg.operator as string] ?? String(cfg.operator);
    return `${metric} ${op} ${cfg.threshold}`;
  }
  if (rule.trigger_type === 'node_state') {
    return `État : ${rule.trigger_config.state}`;
  }
  return rule.trigger_type;
}

export function formatScope(rule: AutomationRule): string {
  if (rule.target_group) return `Groupe : ${rule.target_group}`;
  if (rule.target_node_id) return 'Nœud spécifique';
  return 'Tous les nœuds';
}

export function formatDate(ts: number | null): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

export interface StatCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  highlight?: boolean;
}