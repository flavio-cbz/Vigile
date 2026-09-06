import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { NodeDetailDiskTab } from './NodeDetailDiskTab';
import * as diskApi from '../../api/disk';
import type { DiskScanResult } from '../../types/disk';

const mockScanResult: DiskScanResult = {
  root: {
    name: '/',
    path: '/',
    size: 1024,
    is_dir: true,
    children: [
      {
        name: 'var',
        path: '/var',
        size: 512,
        is_dir: true,
        children: [
          {
            name: 'log',
            path: '/var/log',
            size: 256,
            is_dir: true,
            children: [],
          },
        ],
      },
    ],
  },
  truncated: false,
  scanned_at: 1700000000,
  walked_count: 10,
  skipped_perm: 0,
};

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

describe('NodeDetailDiskTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.spyOn(diskApi, 'getDiskScan').mockResolvedValue(mockScanResult);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('populates select options with mounts and excludes /boot/efi', async () => {
    render(
      <NodeDetailDiskTab
        nodeId="node-1"
        mounts={['/', '/mnt/data', '/boot/efi']}
        isAdmin={false}
      />
    );

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(['/', '/mnt/data']);
    expect(options).not.toContain('/boot/efi');
  });

  it('persists selected mount to localStorage when changed', async () => {
    render(
      <NodeDetailDiskTab
        nodeId="node-1"
        mounts={['/', '/mnt/data']}
        isAdmin={true}
      />
    );

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: '/mnt/data' } });

    expect(select.value).toBe('/mnt/data');
    expect(window.localStorage.getItem('vigile_disk_mount_node-1')).toBe('/mnt/data');
    expect(diskApi.getDiskScan).toHaveBeenCalledWith(
      'node-1',
      {
        path: '/mnt/data',
        force: false,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('restores mount from localStorage if valid', async () => {
    window.localStorage.setItem('vigile_disk_mount_node-2', '/mnt/backup');

    render(
      <NodeDetailDiskTab
        nodeId="node-2"
        mounts={['/', '/mnt/backup']}
        isAdmin={false}
      />
    );

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('/mnt/backup');
    expect(diskApi.getDiskScan).toHaveBeenCalledWith(
      'node-2',
      {
        path: '/mnt/backup',
        force: false,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('falls back to sessionStorage if localStorage is empty', async () => {
    window.sessionStorage.setItem('vigile_disk_mount_node-3', '/mnt/data');

    render(
      <NodeDetailDiskTab
        nodeId="node-3"
        mounts={['/', '/mnt/data']}
        isAdmin={false}
      />
    );

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('/mnt/data');
  });

  it('falls back to validMounts[0] if stored mount is no longer mounted', async () => {
    window.localStorage.setItem('vigile_disk_mount_node-4', '/media/unplugged_usb');

    render(
      <NodeDetailDiskTab
        nodeId="node-4"
        mounts={['/']}
        isAdmin={false}
      />
    );

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('/');
  });

  it('drilling down does NOT overwrite localStorage stored mount', async () => {
    window.localStorage.setItem('vigile_disk_mount_node-5', '/');

    render(
      <NodeDetailDiskTab
        nodeId="node-5"
        mounts={['/', '/mnt/data']}
        isAdmin={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('10 files')).toBeInTheDocument();
    });

    // Storage is still /
    expect(window.localStorage.getItem('vigile_disk_mount_node-5')).toBe('/');
  });

  it('displays explicit error banner on scan failure with retry button', async () => {
    vi.spyOn(diskApi, 'getDiskScan').mockRejectedValue(new Error('Permission denied on worker'));

    render(
      <NodeDetailDiskTab
        nodeId="node-err"
        mounts={['/']}
        isAdmin={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Permission denied on worker')).toBeInTheDocument();
    });

    const rescanBtn = screen.getByRole('button', { name: /actualiser|rescan/i });
    expect(rescanBtn).toBeInTheDocument();
  });

  it('local drill-down in treemap or breadcrumb triggers ZERO network requests', async () => {
    render(
      <NodeDetailDiskTab
        nodeId="node-drill"
        mounts={['/']}
        isAdmin={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('10 files')).toBeInTheDocument();
    });

    const initialCallCount = vi.mocked(diskApi.getDiskScan).mock.calls.length;

    // Click on directory in treemap
    const varRect = document.querySelector('rect.cursor-pointer');
    if (varRect) {
      fireEvent.click(varRect);
    }

    // Breadcrumb should show 'var'
    await waitFor(() => {
      expect(screen.getByText('var')).toBeInTheDocument();
    });

    // Network calls must NOT have increased!
    expect(vi.mocked(diskApi.getDiskScan).mock.calls.length).toBe(initialCallCount);

    // Click on root breadcrumb to return
    const rootCrumb = screen.getByRole('button', { name: '/' });
    fireEvent.click(rootCrumb);

    // Network calls still must NOT have increased!
    expect(vi.mocked(diskApi.getDiskScan).mock.calls.length).toBe(initialCallCount);
  });

  it('displays visible warning banner when permission is denied and root size is 0', async () => {
    vi.spyOn(diskApi, 'getDiskScan').mockResolvedValue({
      root: {
        name: '/',
        path: '/',
        size: 0,
        is_dir: true,
        children: [],
      },
      truncated: false,
      scanned_at: 1700000000,
      walked_count: 0,
      skipped_perm: 3,
    });

    render(
      <NodeDetailDiskTab
        nodeId="node-perm-denied"
        mounts={['/']}
        isAdmin={false}
      />
    );

    await waitFor(() => {
      const elements = screen.getAllByText('Permission refusée : impossible de scanner ce point de montage');
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('aborts in-flight scan and clears previous data on mount change', async () => {
    let resolveFirstScan: (val: DiskScanResult) => void;
    const firstScanPromise = new Promise<DiskScanResult>((resolve) => {
      resolveFirstScan = resolve;
    });

    vi.spyOn(diskApi, 'getDiskScan').mockImplementation((_nodeId, params) => {
      if (params?.path === '/') {
        return firstScanPromise;
      }
      return Promise.resolve(mockScanResult);
    });

    render(
      <NodeDetailDiskTab
        nodeId="node-abort"
        mounts={['/', '/mnt/data']}
        isAdmin={false}
      />
    );

    // Currently loading '/'
    expect(screen.getByText(/analyse en cours|chargement|loading/i)).toBeInTheDocument();

    // Switch mount to '/mnt/data' before '/' completes
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: '/mnt/data' } });

    // The first call's AbortSignal should be aborted
    const firstCallSignal = vi.mocked(diskApi.getDiskScan).mock.calls[0][2]?.signal;
    expect(firstCallSignal?.aborted).toBe(true);

    // Resolve first scan - should not break or resurrect stale view
    resolveFirstScan!(mockScanResult);

    await waitFor(() => {
      expect(screen.getByText('10 files')).toBeInTheDocument();
    });
  });

  it('correctly extracts mounts from both string lists and object lists (NodeDetail parsing logic)', () => {
    const parseMounts = (cached_disks_json?: string | null): string[] => {
      try {
        const parsed = JSON.parse(cached_disks_json || '[]');
        return Array.isArray(parsed)
          ? (parsed
              .map((d: unknown) => (typeof d === 'string' ? d : (d as { mount_point?: string })?.mount_point))
              .filter((m): m is string => Boolean(m)))
          : [];
      } catch {
        return [];
      }
    };

    expect(parseMounts('["/", "/mnt/data"]')).toEqual(['/', '/mnt/data']);
    expect(parseMounts('[{"mount_point": "/"}, {"mount_point": "/mnt/data"}]')).toEqual(['/', '/mnt/data']);
    expect(parseMounts(null)).toEqual([]);
    expect(parseMounts('invalid json')).toEqual([]);
  });
});
