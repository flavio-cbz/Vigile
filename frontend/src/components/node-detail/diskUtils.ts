import type { DiskMount } from './types';

export interface DiskEstimation {
  days_left: number | null;
  growth_gb_per_day: number;
  confidence: 'none' | 'low' | 'medium' | 'high';
  hours_collected?: number;
  is_noisy?: boolean;
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
  const byMount: Record<
    string,
    { points: { ts: number; used_bytes: number; total_bytes: number }[] }
  > = {};

  for (const snapshot of history) {
    if (!snapshot.disks || snapshot.disks.length === 0) continue;
    // collected_at is in seconds
    const tsMs = (snapshot.collected_at || 0) * 1000;
    if (tsMs === 0) continue;

    for (const disk of snapshot.disks) {
      if (!disk.mount_point) continue;
      if (!byMount[disk.mount_point]) {
        byMount[disk.mount_point] = { points: [] };
      }
      byMount[disk.mount_point].points.push({
        ts: tsMs,
        used_bytes: disk.used_bytes,
        total_bytes: disk.total_bytes,
      });
    }
  }

  for (const [mountPoint, data] of Object.entries(byMount)) {
    if (data.points.length < 4) continue;

    // Sort chronologically ascending (t0 = oldest, tEnd = newest)
    const sortedPoints = [...data.points].sort((a, b) => a.ts - b.ts);

    // Deduplicate by timestamp if multiple snapshots share the exact same timestamp
    const deduped: { ts: number; used_bytes: number; total_bytes: number }[] = [];
    for (const p of sortedPoints) {
      if (deduped.length > 0 && deduped[deduped.length - 1].ts === p.ts) {
        deduped[deduped.length - 1] = p;
      } else {
        deduped.push(p);
      }
    }

    if (deduped.length < 4) continue;

    const timestamps = deduped.map((p) => p.ts);
    const yRaw = deduped.map((p) => p.used_bytes / (1024 ** 3));
    const totalBytes = deduped[deduped.length - 1].total_bytes;
    const lastUsedGB = yRaw[yRaw.length - 1];
    const freeBytes = Math.max(0, totalBytes - lastUsedGB * (1024 ** 3));

    // Calculate timespan in hours & days
    const t0 = timestamps[0];
    const tEnd = timestamps[timestamps.length - 1];
    const timespanMs = tEnd - t0;
    const hoursCollected = timespanMs / 3600000;
    const roundedHours = Math.round(hoursCollected * 10) / 10;

    // If less than 2 hours of data collected for this disk, don't display noisy slope
    if (hoursCollected < 2 || timespanMs <= 0) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence: 'none',
        hours_collected: roundedHours,
      };
      continue;
    }

    // Determine baseline confidence by observation timespan
    let confidence: 'none' | 'low' | 'medium' | 'high' = 'low';
    if (hoursCollected >= 24) {
      confidence = 'high';
    } else if (hoursCollected >= 6) {
      confidence = 'medium';
    }

    // Normalize timestamps to days from first measurement
    const x = timestamps.map((t) => (t - t0) / 86400000);

    // IQR outlier detection on consecutive deltas. Outlier deltas are treated
    // as PERMANENT LEVEL SHIFTS (mass deletion / bulk import), not noise: the
    // series is rebuilt backwards from the latest value ignoring those jumps,
    // so a mass deletion doesn't zero out the real growth estimate.
    // Mirrors master/core/insights.py for consistency.
    const deltas = yRaw.slice(1).map((v, i) => v - yRaw[i]);
    const sortedDeltas = [...deltas].sort((a, b) => a - b);
    const nDeltas = sortedDeltas.length;
    if (nDeltas < 3) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence: 'low',
        hours_collected: roundedHours,
      };
      continue;
    }
    const q1 = sortedDeltas[Math.floor(nDeltas * 0.25)];
    const q3 = sortedDeltas[Math.min(nDeltas - 1, Math.floor(nDeltas * 0.75))];
    const iqr = q3 - q1;
    const lower = q1 - 1.5 * iqr;
    const upper = q3 + 1.5 * iqr;
    const inlierCount = deltas.reduce((acc, d) => (d >= lower && d <= upper ? acc + 1 : acc), 0);
    if (inlierCount < 3) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence: 'low',
        hours_collected: roundedHours,
        is_noisy: true,
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
    const roundedSlope = Math.round(slope * 1000) / 1000;

    // Calculate R² (coefficient of determination) matching master/core/insights.py
    const yMean = sumY / n;
    const ssTot = y.reduce((acc, yi) => acc + (yi - yMean) ** 2, 0);
    const intercept = (sumY - slope * sumX) / n;
    const ssRes = y.reduce((acc, yi, i) => acc + (yi - (slope * x[i] + intercept)) ** 2, 0);
    const rSquared = ssTot > 1e-9 ? 1.0 - ssRes / ssTot : 0.0;

    const isNoisy = rSquared < 0.5 && timespanMs >= 21600000 && Math.abs(roundedSlope) > 0.05;
    if (isNoisy) {
      confidence = 'low';
    }

    // Truly flat slope (|slope| <= 0.0001 GB/day)
    if (Math.abs(slope) <= 0.0001) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: 0,
        confidence,
        hours_collected: roundedHours,
        is_noisy: isNoisy,
      };
      continue;
    }

    // Shrinking disk (negative slope)
    if (slope < 0) {
      result[mountPoint] = {
        days_left: null,
        growth_gb_per_day: roundedSlope,
        confidence,
        hours_collected: roundedHours,
        is_noisy: isNoisy,
      };
      continue;
    }

    const freeGB = freeBytes / (1024 ** 3);
    const daysLeft = freeGB > 0 ? freeGB / slope : 0;

    result[mountPoint] = {
      days_left: isFinite(daysLeft) && daysLeft >= 0 ? Math.round(daysLeft) : null,
      growth_gb_per_day: roundedSlope,
      confidence,
      hours_collected: roundedHours,
      is_noisy: isNoisy,
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
  confidence?: 'none' | 'low' | 'medium' | 'high',
  observationReady?: boolean,
): 'collecting' | 'estimating' | 'ready' {
  if (observationReady === false || confidence === 'none' || confidence === undefined) return 'collecting';
  if (confidence === 'low') return 'estimating';
  return 'ready';
}
