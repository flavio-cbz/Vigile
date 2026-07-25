export interface DiskNode {
  name: string;
  path: string;
  size: number;
  is_dir: boolean;
  children?: DiskNode[];
}

export interface DiskScanResult {
  root: DiskNode;
  truncated: boolean;
  scanned_at: number;
  walked_count: number;
  skipped_perm: number;
}
