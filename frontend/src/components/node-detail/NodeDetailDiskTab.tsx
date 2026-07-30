import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, HardDrive, ChevronRight, AlertTriangle } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import { getDiskScan } from '../../api/disk';
import type { DiskScanResult } from '../../types/disk';
import { DiskTreemap } from './DiskTreemap';

interface NodeDetailDiskTabProps {
  nodeId: string | undefined;
  mounts: string[];
  isAdmin: boolean;
}

export const NodeDetailDiskTab: React.FC<NodeDetailDiskTabProps> = ({
  nodeId,
  mounts,
  isAdmin,
}) => {
  const { t } = useLocale();
  const [selectedPath, setSelectedPath] = useState(mounts[0] ?? '/');
  const [scanResult, setScanResult] = useState<DiskScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchScan = useCallback(
    async (force = false) => {
      if (!nodeId) return;
      setLoading(true);
      setError(null);
      try {
        const result = await getDiskScan(nodeId, {
          path: selectedPath,
          force,
        });
        if (result) {
          setScanResult(result);
        } else {
          setError(t('node_detail.disk.error'));
        }
      } catch {
        setError(t('node_detail.disk.error'));
      } finally {
        setLoading(false);
      }
    },
    [nodeId, selectedPath, t],
  );

  useEffect(() => {
    if (nodeId) {
      void fetchScan();
    }
  }, [nodeId, fetchScan]);

  const handleDrill = useCallback(
    (path: string) => {
      setSelectedPath(path);
    },
    [],
  );

  const breadcrumb = selectedPath
    .split('/')
    .filter(Boolean)
    .reduce<{ label: string; path: string }[]>((acc, segment) => {
      const parentPath = acc.length > 0 ? `${acc[acc.length - 1].path}/${segment}` : `/${segment}`;
      acc.push({ label: segment, path: parentPath });
      return acc;
    }, []);

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg">
        <div className="flex items-center gap-3 font-interface text-xs">
          <HardDrive className="w-4 h-4 text-text-3" />

          {/* Path selector */}
          <select
            value={selectedPath}
            onChange={(e) => setSelectedPath(e.target.value)}
            className="bg-surface-2 border border-border rounded px-3 py-1.5 focus:outline-none text-text-2 font-semibold"
          >
            {mounts.length > 0
              ? mounts.map((m) => (
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
              onClick={() => void fetchScan(true)}
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
            onClick={() => setSelectedPath('/')}
            className="hover:text-accent cursor-pointer transition-colors"
          >
            /
          </button>
          {breadcrumb.map((crumb, idx) => (
            <React.Fragment key={crumb.path}>
              <ChevronRight className="w-3 h-3 text-text-3/50" />
              <button
                onClick={() => setSelectedPath(crumb.path)}
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
          <p>{error}</p>
          <button
            onClick={() => void fetchScan()}
            className="px-3 py-1.5 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent rounded cursor-pointer transition-all duration-150"
          >
            {t('node_detail.disk.rescan')}
          </button>
        </div>
      ) : scanResult ? (
        /* Treemap */
        <div className="border border-border rounded-xl bg-surface overflow-hidden shadow">
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
            <DiskTreemap root={scanResult.root} onDrill={handleDrill} />
          </div>
        </div>
      ) : null}

      {/* Propose cleanup button */}
      {scanResult && (
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