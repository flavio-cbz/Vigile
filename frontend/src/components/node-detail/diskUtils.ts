import type { DiskMount } from './types';

interface DiskEstimation {
  days_left: number | null;
  growth_gb_per_day: number;
  confidence: 'none' | 'low' | 'medium' | 'high';
}

/**
 * Linear regression on disk usage history per mount point.
 * Returns an estimation of when the disk will be full.
 *
 * Uses the same algorithm as master/core/insights.py for consistency:
 * - y = used_bytes_gb over time
 * - x = time in days from first snapshot
 * - slope = GB/day growth rate
 * - days_left = (total - used) / slope
 */
export function estimateDiskSaturation(
  history: DiskMount[][],
): Record<string, DiskEstimation> {
  const result: Record<string, DiskEstimation> = {};

  if (history.length < 4) {
    return result;
  }

  // Group by mount_point
  const byMount: Record<string, { timestamps: number[]; used_gb: number[]; total_bytes: number }> = {};

  for (const snapshot of history) {
    for (const disk of snapshot) {
      if (!byMount[disk.mount_point]) {
        byMount[disk.mount_point] = { timestamps: [], used_gb: [], total_bytes: disk.total_bytes };
      }
      const entry = byMount[disk.mount_point];
      // Use the current time as a rough proxy for timestamp
      // In production, StatsPoint.time should be parsed to epoch
      entry.timestamps.push(Date.now());
      entry.used_gb.push(disk.used_bytes / 1024 ** 3);
    }
  }

  for (const [mountPoint, data] of Object.entries(byMount)) {
    if (data.timestamps.length < 4) continue;

    const totalBytes = data.total_bytes;
    const freeBytes = totalBytes - data.used_gb[data.used_gb.length - 1] * 1024 ** 3;

    // Normalize timestamps to days from first measurement
    const t0 = data.timestamps[0];
    const x = data.timestamps.map((t) => (t - t0) / 86400000);
    const y = data.used_gb;

    const n = x.length;
    let sumX = 0;
    let sumY = 0;
    let sumXX = 0;
    let sumXY = 0;

    for (let i = 0; i < n; i++) {
      sumX += x[i];
      sumY += y[i];
      sumXX += x[i] * x[i];
      sumXY += x[i] * y[i];
    }

    const denominator = n * sumXX - sumX * sumX;
    if (Math.abs(denominator) < 1e-10) continue;

    const slope = (n * sumXY - sumX * sumY) / denominator;

    if (slope <= 0.001) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence: 'high',
      };
      continue;
    }

    const freeGB = freeBytes / 1024 ** 3;
    const daysLeft = freeGB / slope;


    let confidence: 'none' | 'low' | 'medium' | 'high' = 'low';
    const hoursCollected = (data.timestamps[data.timestamps.length - 1] - data.timestamps[0]) / 3600000;
    if (hoursCollected >= 24) {
      confidence = n >= 7 ? 'high' : 'medium';
    }
    if (hoursCollected < 6) {
      confidence = 'none';
    }

    result[mountPoint] = {
      days_left: isFinite(daysLeft) && daysLeft > 0 ? Math.round(daysLeft) : null,
      growth_gb_per_day: Math.round(slope * 1000) / 1000,
      confidence,
    };
  }

  return result;
}

/**
 * Combine percent and days_left into a single severity level.
 */
export function getDiskSeverity(
  percent: number,
  daysLeft: number | null,
): 'ok' | 'warning' | 'critical' {
  // If we have no estimation, rely on percent only
  if (daysLeft === null) {
    if (percent > 90) return 'critical';
    if (percent > 75) return 'warning';
    return 'ok';
  }

  // Critical: >90% full OR < 3 days remaining
  if (percent > 90 || daysLeft < 3) return 'critical';
  // Warning: >75% OR < 14 days
  if (percent > 75 || daysLeft < 14) return 'warning';
  return 'ok';
}
