import { api } from '../hooks/useApi';
import type { DiskScanResult } from '../types/disk';

export interface GetDiskScanParams {
  path?: string;
  force?: boolean;
  max_depth?: number;
  min_size_bytes?: number;
}

export const getDiskScan = (
  nodeId: string,
  params?: GetDiskScanParams,
): Promise<DiskScanResult | null> => {
  const searchParams = new URLSearchParams();
  if (params?.path) searchParams.set('path', params.path);
  if (params?.force) searchParams.set('force', '1');
  if (params?.max_depth !== undefined) searchParams.set('max_depth', String(params.max_depth));
  if (params?.min_size_bytes !== undefined) searchParams.set('min_size_bytes', String(params.min_size_bytes));
  const qs = searchParams.toString();
  return api<DiskScanResult>(`/api/nodes/${nodeId}/disk-scan${qs ? `?${qs}` : ''}`);
};
