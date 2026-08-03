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
  history: { collected_at?: number; disks?: DiskMount[] }[],
): Record<string, DiskEstimation> {
  const result: Record<string, DiskEstimation> = {};

  if (!history || history.length < 4) {
    return result;
  }

  // Group by mount_point using real collected_at timestamps
  const byMount: Record<string, { timestamps: number[]; used_gb: number[]; total_bytes: number }> = {};

  for (const snapshot of history) {
    if (!snapshot.disks || snapshot.disks.length === 0) continue;
    // collected_at is in seconds
    const tsMs = (snapshot.collected_at || 0) * 1000;
    if (tsMs === 0) continue;

    for (const disk of snapshot.disks) {
      if (!byMount[disk.mount_point]) {
        byMount[disk.mount_point] = { timestamps: [], used_gb: [], total_bytes: disk.total_bytes };
      }
      const entry = byMount[disk.mount_point];
      entry.timestamps.push(tsMs);
      entry.used_gb.push(disk.used_bytes / (1024 ** 3));
    }
  }

  for (const [mountPoint, data] of Object.entries(byMount)) {
    if (data.timestamps.length < 4) continue;

    const totalBytes = data.total_bytes;
    const lastUsedGB = data.used_gb[data.used_gb.length - 1];
    const freeBytes = totalBytes - lastUsedGB * (1024 ** 3);

    // Calculate timespan in hours & days
    const t0 = data.timestamps[0];
    const tEnd = data.timestamps[data.timestamps.length - 1];
    const timespanMs = tEnd - t0;
    const hoursCollected = timespanMs / 3600000;

    // If less than 2 hours of data collected for this disk, don't display noisy slope
    if (hoursCollected < 2 || timespanMs <= 0) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence: 'none',
      };
      continue;
    }

    // Normalize timestamps to days from first measurement
    const x = data.timestamps.map((t) => (t - t0) / 86400000);
    const yRaw = data.used_gb;

    // IQR outlier detection on consecutive deltas. Outlier deltas are treated
    // as PERMANENT LEVEL SHIFTS (mass deletion / bulk import), not noise: the
    // series is rebuilt backwards from the latest value ignoring those jumps,
    // so a mass deletion doesn't zero out the real growth estimate.
    // Mirrors master/core/insights.py for consistency.
    const deltas = yRaw.slice(1).map((v, i) => v - yRaw[i]);
    const sortedDeltas = [...deltas].sort((a, b) => a - b);
    const nDeltas = sortedDeltas.length;
    const q1 = sortedDeltas[Math.floor((nDeltas + 3) / 4) - 1];
    const q3 = sortedDeltas[Math.floor((3 * nDeltas + 3) / 4) - 1];
    const iqr = q3 - q1;
    const lower = q1 - 1.5 * iqr;
    const upper = q3 + 1.5 * iqr;
    const inlierCount = deltas.reduce((acc, d) => (d >= lower && d <= upper ? acc + 1 : acc), 0);
    if (inlierCount < 3) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence: 'low',
      };
      continue;
    }
    const y = new Array<number>(yRaw.length);
    y[yRaw.length - 1] = yRaw[yRaw.length - 1];
    for (let i = yRaw.length - 2; i >= 0; i--) {
      const d = yRaw[i + 1] - yRaw[i];
      y[i] = d >= lower && d <= upper ? y[i + 1] - d : y[i + 1];
    }

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

    // If disk usage is flat or shrinking (slope <= 0.01 GB/day)
    if (slope <= 0.01) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence: hoursCollected >= 24 ? 'high' : 'medium',
      };
      continue;
    }

    const freeGB = freeBytes / (1024 ** 3);
    const daysLeft = freeGB / slope;

    let confidence: 'none' | 'low' | 'medium' | 'high' = 'low';
    if (hoursCollected >= 24) {
      confidence = 'high';
    } else if (hoursCollected >= 6) {
      confidence = 'medium';
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

/**
 * Determine whether a disk mount has enough observation data for estimation.
 */
export function getDiskObservationStatus(
  daysLeft: number | null | undefined,
  observationReady: boolean,
): 'collecting' | 'estimating' | 'ready' {
  if (!observationReady) return 'collecting';
  if (daysLeft === undefined || daysLeft === null) return 'estimating';
  return 'ready';
}
