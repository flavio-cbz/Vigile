import type { LucideIcon } from 'lucide-react';

/** Response from GET /api/auth/me */
export interface MeResponse {
  username: string;
  role: string;
  user_id: string;
}

/** Shape of react-router location.state on the login page */
export interface LoginLocationState {
  from?: {
    pathname: string;
  };
}

/** A sidebar navigation item definition */
export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
  badge?: number;
  dot?: boolean;
}

/** Node metrics returned by bulk status endpoint */
export interface NodeMetrics {
  cpu: number | null;
  mem: number | null;
  disk: number | null;
}

/** Audit entry details — server-defined key-value pairs */
export type AuditDetails = Record<string, unknown>;

/** Response shape from approve/reject proposal endpoints */
export interface ProposalActionResponse {
  success?: boolean;
  detail?: string;
}
