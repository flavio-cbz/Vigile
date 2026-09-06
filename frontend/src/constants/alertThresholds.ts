/**
 * Centralized metric alert thresholds — single source of truth mirroring
 * master/core/alert_engine.py BUILTIN_THRESHOLDS.
 *
 * cpu: AlertThreshold("cpu_high_percent",  warning 80 / critical 95 / resolve 60)
 * ram: AlertThreshold("memory_usage_high", warning 85 / critical 95 / resolve 80)
 * disk: AlertThreshold("disk_usage_high", warning 85 / critical 95 / resolve 80)
 */
export const METRIC_ALERT_THRESHOLDS = {
  cpu: { warning: 80, critical: 95, resolve: 60, unit: '%' },
  ram: { warning: 85, critical: 95, resolve: 80, unit: '%' },
  disk: { warning: 85, critical: 95, resolve: 80, unit: '%' },
} as const;

export type MetricAlertThreshold = (typeof METRIC_ALERT_THRESHOLDS)[keyof typeof METRIC_ALERT_THRESHOLDS];
export type MetricKind = keyof typeof METRIC_ALERT_THRESHOLDS;
