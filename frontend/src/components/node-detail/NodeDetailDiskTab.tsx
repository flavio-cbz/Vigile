import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, HardDrive, ChevronRight, AlertTriangle } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { Banner } from '../blocks/Banner';
import { t } from '../../i18n';
import { getDiskScan } from '../../api/disk';
import type { DiskNode, DiskScanResult } from '../../types/disk';
import { DiskTreemap } from './DiskTreemap';

export function findDiskNodeByPath(root: DiskNode, targetPath: string): DiskNode | null {
  if (root.path === targetPath) return root;
  if (!root.children || root.children.length === 0) return null;
  for (const child of root.children) {
    if (child.path === targetPath) return child;
    const found = findDiskNodeByPath(child, targetPath);
    if (found) return found;
  }
  return null;
}

interface NodeDetailDiskTabProps {
  nodeId: string | undefined;
  mounts: string[];
  isAdmin: boolean;
}

const getStoredMount = (nodeId: string): string | null => {
  try {
    const val = window.localStorage.getItem(`vigile_disk_mount_${nodeId}`);
    if (val) return val;
  } catch {
    // localStorage unavailable, try sessionStorage
  }
  try {
    return window.sessionStorage.getItem(`vigile_disk_mount_${nodeId}`);
  } catch {
    return null;
  }
};

const setStoredMount = (nodeId: string, mount: string): void => {
  try {
    window.localStorage.setItem(`vigile_disk_mount_${nodeId}`, mount);
  } catch {
    try {
      window.sessionStorage.setItem(`vigile_disk_mount_${nodeId}`, mount);
    } catch {
      // Storage unavailable, ignore
    }
  }
};

const resolveInitialMount = (nodeId: string | undefined, validMounts: string[]): string => {
  if (validMounts.length === 0) return '/';
  if (!nodeId) return validMounts[0] ?? '/';
  const stored = getStoredMount(nodeId);
  if (stored && validMounts.includes(stored)) {
    return stored;
  }
  return validMounts[0] ?? '/';
};

export const NodeDetailDiskTab: React.FC<NodeDetailDiskTabProps> = ({
  nodeId,
  mounts,
  isAdmin,
}) => {
  const validMounts = useMemo(
    () => mounts.filter((m) => m !== '/boot/efi'),
    [mounts]
  );

  const [selectedMount, setSelectedMount] = useState<string>(() =>
    resolveInitialMount(nodeId, validMounts)
  );
  const [drillPath, setDrillPath] = useState<string>(() =>
    resolveInitialMount(nodeId, validMounts)
  );
  const [scanResult, setScanResult] = useState<DiskScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Sync with nodeId change (switch between different nodes)
  useEffect(() => {
    if (validMounts.length === 0) return;
    const initial = resolveInitialMount(nodeId, validMounts);
    setSelectedMount(initial);
    setDrillPath(initial);
  }, [nodeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Guard against unmounted partitions: fallback if current mount no longer exists
  useEffect(() => {
    if (validMounts.length === 0) return;
    const isMountValid = validMounts.includes(selectedMount);
    if (!isMountValid) {
      const fallback = resolveInitialMount(nodeId, validMounts);
      setSelectedMount(fallback);
      setDrillPath(fallback);
      if (nodeId) {
        setStoredMount(nodeId, fallback);
      }
    }
  }, [validMounts, selectedMount, nodeId]);

  const fetchScan = useCallback(
    async (mountToScan: string, force = false) => {
      if (!nodeId) return;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setLoading(true);
      setError(null);
      try {
        const result = await getDiskScan(
          nodeId,
          {
            path: mountToScan,
            force,
          },
          { signal: controller.signal }
        );
        if (controller.signal.aborted) return;
        if (result) {
          setScanResult(result);
        } else {
          setError(t('node_detail.disk.error'));
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        if (err instanceof Error && err.name === 'AbortError') return;
        if (err instanceof Error && err.message === 'Request timed out' && controller.signal.aborted) return;
        if (err instanceof Error && err.message) {
          setError(err.message);
        } else {
          setError(t('node_detail.disk.error'));
        }
      } finally {
        if (abortControllerRef.current === controller) {
          setLoading(false);
        }
      }
    },
    [nodeId]
  );

  useEffect(() => {
    if (nodeId && selectedMount) {
      void fetchScan(selectedMount);
    }
  }, [nodeId, selectedMount, fetchScan]);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleMountChange = (newMount: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setScanResult(null);
    setError(null);
    setSelectedMount(newMount);
    setDrillPath(newMount);
    if (nodeId) {
      setStoredMount(nodeId, newMount);
    }
  };

  const handleDrill = useCallback((path: string) => {
    // Drill-down updates viewing path only; NEVER overwrite selectedMount or storage, NEVER fetch!
    setDrillPath(path);
  }, []);

  const currentTreeRoot = useMemo(() => {
    if (!scanResult?.root) return null;
    if (!drillPath || drillPath === selectedMount) return scanResult.root;
    return findDiskNodeByPath(scanResult.root, drillPath) ?? scanResult.root;
  }, [scanResult, drillPath, selectedMount]);

  const breadcrumb = useMemo(() => {
    if (!drillPath || drillPath === selectedMount) return [];
    const base = selectedMount.replace(/\/$/, '');
    const rel = drillPath.startsWith(selectedMount)
      ? drillPath.slice(selectedMount.length).replace(/^\//, '')
      : drillPath.replace(/^\//, '');
    const segments = rel.split('/').filter(Boolean);
    const crumbs: { label: string; path: string }[] = [];
    let cur = base;
    for (const seg of segments) {
      cur = `${cur}/${seg}`;
      crumbs.push({ label: seg, path: cur });
    }
    return crumbs;
  }, [drillPath, selectedMount]);

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg">
        <div className="flex items-center gap-3 font-interface text-xs">
          <HardDrive className="w-4 h-4 text-text-3" />

          {/* Path selector */}
          <select
            value={selectedMount}
            onChange={(e) => handleMountChange(e.target.value)}
            className="bg-surface-2 border border-border rounded px-3 py-1.5 focus:outline-none text-text-2 font-semibold"
          >
            {validMounts.length > 0
              ? validMounts.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))
              : (
                  <option value="/">/</option>
                )
            }
          </select>
        </div>

        <div className="flex items-center gap-2">
          {isAdmin && (
            <button
              onClick={() => void fetchScan(selectedMount, true)}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent hover:bg-accent/5 rounded cursor-pointer disabled:opacity-50 transition-all duration-150"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              {t('node_detail.disk.rescan')}
            </button>
          )}
        </div>
      </div>

      {/* Breadcrumb */}
      {breadcrumb.length > 0 && (
        <div className="flex items-center gap-1 font-mono text-[10px] text-text-3 px-1">
          <button
            onClick={() => setDrillPath(selectedMount)}
            className="hover:text-accent cursor-pointer transition-colors"
          >
            {selectedMount}
          </button>
          {breadcrumb.map((crumb, idx) => (
            <React.Fragment key={crumb.path}>
              <ChevronRight className="w-3 h-3 text-text-3/50" />
              <button
                onClick={() => setDrillPath(crumb.path)}
                className={`hover:text-accent cursor-pointer transition-colors ${
                  idx === breadcrumb.length - 1 ? 'text-text-1 font-bold' : ''
                }`}
              >
                {crumb.label}
              </button>
            </React.Fragment>
          ))}
        </div>
      )}

      {/* Truncated warning */}
      {scanResult?.truncated && (
        <div className="flex items-center gap-2 px-3 py-2 bg-[var(--color-warning, #f59e0b)]/10 border border-[var(--color-warning, #f59e0b)]/20 rounded text-xs text-[var(--color-warning, #f59e0b)] font-interface">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {t('node_detail.disk.truncated')}
        </div>
      )}

      {/* Loading */}
      {loading && !scanResult ? (
        <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
          <Spinner size="sm" />
          <span className="font-interface text-xs">{t('node_detail.disk.loading')}</span>
        </div>
      ) : error ? (
        /* Error */
        <div className="py-12 text-center text-text-3 text-xs bg-surface/20 border border-border rounded-lg space-y-3">
          <div className="flex items-center justify-center gap-2 text-warning">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <p className="font-interface font-semibold">{error}</p>
          </div>
          <button
            onClick={() => void fetchScan(selectedMount)}
            className="px-3 py-1.5 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent rounded cursor-pointer transition-all duration-150"
          >
            {t('node_detail.disk.rescan')}
          </button>
        </div>
      ) : scanResult && scanResult.skipped_perm > 0 && scanResult.root.size === 0 ? (
        <Banner
          variant="warning"
          title="Permission refusée : impossible de scanner ce point de montage"
          message="Permission refusée : impossible de scanner ce point de montage"
        />
      ) : scanResult ? (
        /* Treemap */
        <div className="border border-border rounded-xl bg-surface overflow-hidden shadow min-h-[280px] sm:min-h-[380px] lg:min-h-[460px]">
          <div className="p-3 border-b border-border flex items-center justify-between">
            <span className="font-interface text-[9px] font-extrabold uppercase tracking-widest text-text-3">
              {t('node_detail.disk.title')}
            </span>
            <span className="font-mono text-[10px] text-text-3">
              {scanResult.walked_count.toLocaleString()} files
              {scanResult.skipped_perm > 0 && ` · ${scanResult.skipped_perm} skipped`}
            </span>
          </div>
          <div className="p-2">
            <DiskTreemap
              root={currentTreeRoot ?? scanResult.root}
              onDrill={handleDrill}
              skippedPerm={scanResult.skipped_perm}
            />
          </div>
        </div>
      ) : null}

      {/* Propose cleanup button */}
      {scanResult && scanResult.root.size > 0 && (
        <div className="flex justify-end">
          <button
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent hover:bg-accent/5 rounded cursor-pointer transition-all duration-150"
          >
            {t('node_detail.disk.propose_cleanup')}
          </button>
        </div>
      )}
    </div>
  );
};