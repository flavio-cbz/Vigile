import { describe, expect, it } from 'vitest';
import { estimateDiskSaturation, getDiskObservationStatus } from './diskUtils';

const GB = 1024 ** 3;

function buildHistory(opts: { snapshots: number; stepGb: number; deletionGb?: number; atIndex?: number }) {
  const { snapshots, stepGb, deletionGb, atIndex = -1 } = opts;
  const t0 = 1_700_000_000;
  let used = 400 * GB;
  const history: { collected_at: number; disks: { mount_point: string; fs_type: string; device: string; total_bytes: number; used_bytes: number; percent: number }[] }[] = [];
  for (let i = 0; i < snapshots; i++) {
    if (i === atIndex) used -= deletionGb! * GB;
    else used += stepGb * GB;
    history.push({
      collected_at: t0 + i * 3600,
      disks: [{ mount_point: '/', fs_type: 'ext4', device: '/dev/sda1', total_bytes: 500 * GB, used_bytes: Math.round(used), percent: 70 }],
    });
  }
  return history;
}

describe('estimateDiskSaturation', () => {
  it('keeps the real growth rate after a mass deletion (level shift)', () => {
    const est = estimateDiskSaturation(buildHistory({ snapshots: 24, stepGb: 2 / 24, deletionGb: 50, atIndex: 12 }));
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.growth_gb_per_day).toBeGreaterThan(1.0);
    expect(disk.growth_gb_per_day).toBeLessThan(5.0);
  });

  it('reports stable (0) when usage is truly flat', () => {
    const est = estimateDiskSaturation(buildHistory({ snapshots: 24, stepGb: 0 }));
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.growth_gb_per_day).toBe(0);
  });

  it('reports negative growth rate when disk space is being freed', () => {
    const est = estimateDiskSaturation(buildHistory({ snapshots: 24, stepGb: -2 / 24 }));
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.growth_gb_per_day).toBeLessThan(0);
  });

  it('returns empty when fewer than 4 snapshots', () => {
    expect(estimateDiskSaturation(buildHistory({ snapshots: 3, stepGb: 0.1 }))).toEqual({});
  });

  // --- NOUVEAUX TESTS (Ticket A5) ---

  it('calculates accurate growth rate and days_left for an increasing slope (pente croissante)', () => {
    // 24 snapshots at 1h intervals, +5 GB per day (+5/24 GB per hour)
    // Starting at 400 GB used out of 500 GB total. After 23h, ~404.8 GB used -> ~95.2 GB free.
    // At +5 GB/day, remaining days = 95.2 / 5 = ~19 days
    const est = estimateDiskSaturation(buildHistory({ snapshots: 24, stepGb: 5 / 24 }));
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.growth_gb_per_day).toBeCloseTo(5.0, 1);
    expect(disk.days_left).toBe(19);
    expect(disk.confidence).toBe('medium');
    expect(disk.hours_collected).toBe(23);
  });

  it('handles flat slope with high confidence (pente plate)', () => {
    const est = estimateDiskSaturation(buildHistory({ snapshots: 48, stepGb: 0 }));
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.growth_gb_per_day).toBe(0);
    expect(disk.days_left).toBeNull();
    expect(disk.confidence).toBe('high');
  });

  it('returns empty object for empty or missing history (historique vide)', () => {
    expect(estimateDiskSaturation([])).toEqual({});
    expect(estimateDiskSaturation(null as unknown as [])).toEqual({});
    expect(estimateDiskSaturation(undefined as unknown as [])).toEqual({});
    expect(estimateDiskSaturation([
      { collected_at: 1700000000, disks: [] },
      { collected_at: 1700003600, disks: [] },
      { collected_at: 1700007200, disks: [] },
      { collected_at: 1700010800, disks: [] },
    ])).toEqual({});
  });

  it('reports confidence "none" when observation timespan is under threshold < 2h (historique sous le seuil)', () => {
    // 4 snapshots spaced by only 10 minutes (30 minutes total < 2 hours)
    const t0 = 1_700_000_000;
    const history = [0, 600, 1200, 1800].map((dt, i) => ({
      collected_at: t0 + dt,
      disks: [{
        mount_point: '/',
        fs_type: 'ext4',
        device: '/dev/sda1',
        total_bytes: 100 * GB,
        used_bytes: (20 + i * 0.1) * GB,
        percent: 20,
      }],
    }));

    const est = estimateDiskSaturation(history);
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.confidence).toBe('none');
    expect(disk.growth_gb_per_day).toBe(0);
    expect(disk.days_left).toBeNull();
    expect(disk.hours_collected).toBe(0.5);
  });

  it('correctly calculates slope with irregularly spaced points (points irrégulièrement espacés)', () => {
    // Non-uniform time steps (gaps between 0.5h and 2.5h) over 30h total
    // Linear growth of +4 GB/day
    const t0 = 1_700_000_000;
    const timeOffsetsHours = [
      0, 0.8, 1.5, 2.7, 4.0, 5.2, 7.0, 8.5, 10.1, 12.0,
      14.3, 16.0, 17.5, 19.8, 22.0, 24.5, 26.2, 28.0, 30.0,
    ];
    const history = timeOffsetsHours.map((h) => {
      const dtSec = h * 3600;
      const days = dtSec / 86400;
      const usedGb = 100 + 4 * days;
      return {
        collected_at: t0 + dtSec,
        disks: [{
          mount_point: '/',
          fs_type: 'ext4',
          device: '/dev/sda1',
          total_bytes: 200 * GB,
          used_bytes: Math.round(usedGb * GB),
          percent: 50,
        }],
      };
    });

    const est = estimateDiskSaturation(history);
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.growth_gb_per_day).toBeCloseTo(4.0, 1);
    expect(disk.confidence).toBe('high');
    expect(disk.days_left).not.toBeNull();
    expect(typeof disk.days_left).toBe('number');
    expect(disk.days_left).toBeGreaterThan(0);
    expect(disk.hours_collected).toBe(30);
  });

  it('handles descending order history correctly (API DESC order)', () => {
    // API returns history in DESC order (newest first). estimateDiskSaturation must sort ascending.
    const ascHistory = buildHistory({ snapshots: 25, stepGb: 3 / 24 });
    const descHistory = [...ascHistory].reverse();

    const est = estimateDiskSaturation(descHistory);
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.growth_gb_per_day).toBeCloseTo(3.0, 1);
    expect(disk.confidence).toBe('high');
    expect(disk.days_left).not.toBeNull();
    expect(disk.days_left).toBeGreaterThan(0);
    expect(disk.hours_collected).toBe(24);
  });

  it('evaluates multiple nodes / mount points with divergent filling trends', () => {
    // Node with 3 distinct mount points:
    // 1) / -> Rapidly filling (+10 GB/day)
    // 2) /var/log -> Stable (0 GB/day)
    // 3) /backup -> Freeing space (-2 GB/day)
    const t0 = 1_700_000_000;
    const history = [];
    for (let i = 0; i < 24; i++) {
      const t = t0 + i * 3600;
      history.push({
        collected_at: t,
        disks: [
          {
            mount_point: '/',
            fs_type: 'ext4',
            device: '/dev/sda1',
            total_bytes: 500 * GB,
            used_bytes: (100 + (10 / 24) * i) * GB,
            percent: 20,
          },
          {
            mount_point: '/var/log',
            fs_type: 'ext4',
            device: '/dev/sda2',
            total_bytes: 50 * GB,
            used_bytes: 10 * GB,
            percent: 20,
          },
          {
            mount_point: '/backup',
            fs_type: 'ext4',
            device: '/dev/sdb1',
            total_bytes: 1000 * GB,
            used_bytes: (800 - (2 / 24) * i) * GB,
            percent: 80,
          },
        ],
      });
    }

    const est = estimateDiskSaturation(history);

    // Root disk /
    expect(est['/']).toBeDefined();
    expect(est['/'].growth_gb_per_day).toBeCloseTo(10.0, 1);
    expect(est['/'].days_left).not.toBeNull();
    expect(est['/'].days_left).toBeGreaterThan(0);

    // /var/log
    expect(est['/var/log']).toBeDefined();
    expect(est['/var/log'].growth_gb_per_day).toBe(0);
    expect(est['/var/log'].days_left).toBeNull();

    // /backup
    expect(est['/backup']).toBeDefined();
    expect(est['/backup'].growth_gb_per_day).toBeCloseTo(-2.0, 1);
    expect(est['/backup'].days_left).toBeNull();
  });

  it('marks is_noisy true and sets confidence low when R² is low on fluctuating history', () => {
    // 6 snapshots with alternating large fluctuations (+100GB, -80GB, +120GB, -110GB, +90GB)
    const t0 = 1_700_000_000;
    const history = [0, 100, 20, 140, 30, 120].map((gb, i) => ({
      collected_at: t0 + i * 3600 * 10,
      disks: [{
        mount_point: '/',
        fs_type: 'ext4',
        device: '/dev/sda1',
        total_bytes: 500 * GB,
        used_bytes: gb * GB,
        percent: 20,
      }],
    }));
    const est = estimateDiskSaturation(history);
    const disk = est['/'];
    expect(disk).toBeDefined();
    expect(disk.confidence).toBe('low');
    expect(disk.is_noisy).toBe(true);
    expect(disk.days_left).not.toBeNull();
  });
});

describe('getDiskObservationStatus', () => {
  it('returns collecting when observationReady is false or confidence is none', () => {
    expect(getDiskObservationStatus('none', true)).toBe('collecting');
    expect(getDiskObservationStatus('high', false)).toBe('collecting');
    expect(getDiskObservationStatus(undefined, true)).toBe('collecting');
  });

  it('returns estimating when confidence is low', () => {
    expect(getDiskObservationStatus('low', true)).toBe('estimating');
  });

  it('returns ready when confidence is medium or high and observationReady is true', () => {
    expect(getDiskObservationStatus('medium', true)).toBe('ready');
    expect(getDiskObservationStatus('high', true)).toBe('ready');
  });
});

