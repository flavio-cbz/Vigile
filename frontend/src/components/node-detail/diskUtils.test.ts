import { describe, expect, it } from 'vitest';
import { estimateDiskSaturation } from './diskUtils';

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

  it('returns empty when fewer than 4 snapshots', () => {
    expect(estimateDiskSaturation(buildHistory({ snapshots: 3, stepGb: 0.1 }))).toEqual({});
  });
});
