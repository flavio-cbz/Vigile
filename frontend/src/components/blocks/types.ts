import type React from 'react';

/**
 * Shared block types for the declarative plugin catalog V2.
 *
 * Contract: docs/contracts/block-contract-v2.md — §1 (MetaSchemaV2 block config),
 * §2 (state-variant matrix), §3 (block context model).
 *
 * Consolidated by J2-T7 (BlockRenderer skeleton): keeps the per-block local
 * definitions that landed with the parallel block components
 * (BlockAction/HoverTokenMap/DataTable/StatusPill/external-auth-popup) and adds
 * the contract-complete BlockConfig / BlockContext / BlockProps / BlockAPI.
 */

// ── Block state variants (contract §2.1) ──

export type BlockState = 'idle' | 'busy' | 'error' | 'empty' | 'data';

/** Alias kept for contract terminology parity (§2.1). */
export type BlockVariant = BlockState;

// ── Block action (contract §4.3) ──

export interface BlockAction {
  /** Human-visible button label. */
  label: string;
  /** Command identifier dispatched when the button is clicked. */
  command: string;
  /**
   * Variant maps to a hover color token.
   * Built-in variants: 'danger' → zinc-800, 'success' → green-custom/10, 'warning' → orange-500/10.
   * Can be overridden per block instance via `hoverTokens`.
   */
  variant: string;
  /** Optional icon override: 'play' | 'square' | 'rotate' | 'trash'. */
  icon?: 'play' | 'square' | 'rotate' | 'trash';
}

// ── Hover token map (contract §4.3) ──

/**
 * Configurable hover tokens keyed by variant name.
 * Defaults: { danger: 'hover:bg-zinc-800', success: 'hover:bg-green-custom/10', warning: 'hover:bg-orange-500/10' }
 */
export interface HoverTokenMap {
  [variant: string]: string;
}

// ── Block config (contract §1) ──

export interface BlockConfig {
  /** Stable block id within the page. */
  id: string;
  /** Block type key dispatched against the component registry, e.g. 'chart-card'. */
  type: string;
  /** Human title. */
  title: string;
  /** Declared route params (manifest PageV2.params). */
  params?: string[];
  /** Context injections requested by the block, e.g. ['node_id'] (contract §3.2). */
  needs?: string[];
  /** Declared state variants (defaults to the full matrix). */
  variants?: BlockState[];
  /** Block-specific configuration (hover tokens, commands, popup size...). */
  config?: Record<string, unknown>;
  /** French empty-state message (contract §2.2, e.g. "Aucun conteneur trouvé"). */
  emptyMessage?: string;
  /** Action button definitions for ActionButtonRow blocks. */
  actions?: BlockAction[];
  /**
   * Hover token overrides keyed by variant name.
   * Merged with built-in defaults; block instances can customize per-token.
   */
  hoverTokens?: HoverTokenMap;
}

// ── Restricted API mirror (contract §3.3) ──

export interface BlockAPI {
  /** Fetch prefixed with /api/plugins/{pluginId}/. */
  fetch<T = unknown>(path: string, options?: RequestInit): Promise<T>;
  /** Relative navigation: /plugins/{pluginId}{path}. */
  navigate(path: string): void;
  /** Absolute navigation inside the Vigile app. */
  navigateGlobal(path: string): void;
  /** Plugin configuration (read-only, Object.freeze). */
  config: Readonly<Record<string, unknown>>;
  /** Translation scoped to plugin (global fallback). */
  t(key: string, params?: Record<string, string | number>): string;
  /** Toast notification. */
  toast(message: string, type?: 'success' | 'error' | 'warning' | 'info'): void;
}

// ── Block context (contract §3) ──

export interface BlockContext {
  /** Route parameters extracted by BlockRenderer from useParams() (§3.1). */
  params: Record<string, string>;
  /** Node ID injected when block declares needs:["node_id"] (§3.2). */
  node_id?: string;
  /** Navigation relative to plugin scope (§3.3). */
  navigate: (path: string) => void;
  /** Absolute navigation within the Vigile app (§3.3). */
  navigateGlobal: (path: string) => void;
  /** Plugin configuration (read-only, Object.freeze) (§3.3). */
  config: Record<string, unknown>;
  /** Toast notification (§3.3). */
  toast: (message: string, type?: 'success' | 'error' | 'warning' | 'info') => void;
  /** Translation function scoped to plugin (§3.3). */
  t: (key: string, params?: Record<string, string | number>) => string;
  /** User roles from session (§3.4). */
  roles: string[];
  /** Restricted plugin API mirror (§3.3). */
  api: BlockAPI;
  /**
   * Souscription SSE à un canal de statut (contract §7.4).
   *
   * Le channel est résolu en endpoint SSE par convention :
   *   `<plugin_id>/<channel_dots_vers_slash>/stream?token=<jwt>`
   *
   * Retourne une fonction de désabonnement (StrictMode-safe : double-invoke
   * ne provoque pas de fuite d'EventSource).
   *
   * Si le channel ne résout pas d'endpoint valide, retourne un no-op unsubscribe.
   */
  subscribeStatus: (
    channel: string,
    cb: (data: Record<string, unknown>) => void,
  ) => () => void;
}

// ── Block props (contract §1/§2) ──

export interface BlockProps {
  /** Block context built by the BlockRenderer. */
  context: BlockContext;
  /** Block configuration. */
  config: BlockConfig;
  /** Current state variant. */
  state: BlockState;
  /** Block data payload (populated when state === 'data'). */
  data: unknown;
  /** Error when state === 'error'. */
  error?: Error | null;
  /** Retry callback for error state. */
  onRetry?: () => void;
}

/** A block component registered in the BlockRenderer registry. */
export type BlockComponent = React.ComponentType<BlockProps>;

// ── Block data/error props (contract §1) ──

export interface BlockDataProps {
  /** Block data payload (populated when state === 'data'). */
  data?: unknown;
  /** Error message when state === 'error'. */
  error?: string;
  /** Retry callback for error state. */
  onRetry?: () => void;
}

// ── Hover token defaults (contract §4.3) ──

export const DEFAULT_HOVER_TOKENS: HoverTokenMap = {
  danger: 'hover:bg-zinc-800',
  success: 'hover:bg-green-custom/10',
  warning: 'hover:bg-orange-500/10',
};

/** Spinner class used in busy state (contract §2.3). */
export const SPINNER_TOKEN = 'border-t-2 border-orange-500';

// ── DataTable column config (contract §1) ──

export interface ColumnConfig<T extends Record<string, unknown> = Record<string, unknown>> {
  /** Row data key to extract cell value */
  key: string;
  /** Human-readable header label */
  label: string;
  /** Text alignment (default: 'left') */
  align?: 'left' | 'center' | 'right';
  /**
   * Optional custom cell renderer (e.g. StatusPill, chips, icons).
   * Falls back to `String(row[key])` when absent.
   */
  render?: (row: T) => React.ReactNode;
}

// ── DataTable props ──

export interface DataTableProps<T extends Record<string, unknown> = Record<string, unknown>> {
  /** Column definitions */
  columns: ColumnConfig<T>[];
  /** Row data array */
  data: T[];
  /** Current block state variant */
  state: BlockState;
  /** Row key selector (defaults to 'id') */
  rowKey?: string;
  /** Empty-state message (default: "Aucun conteneur trouvé") */
  emptyMessage?: string;
  /** Busy-state message (default: "Chargement...") */
  busyMessage?: string;
  /** Error message for error state */
  error?: string;
  /** Retry callback for error state */
  onRetry?: () => void;
  /** Optional row action render slot */
  actions?: (row: T) => React.ReactNode;
}

// ── StatusPill props ──

export interface StatusPillProps {
  /** Status string to display */
  status: string;
  /**
   * List of status values treated as "active" (green pill).
   * Default: ['running', 'active']
   */
  activeStates?: string[];
}

// ── external-auth-popup (contract §7) ──

/**
 * Configuration for the external-auth-popup block (contract §7.1).
 * The block knows only 3 things: start command, cancel command, status channel.
 * It NEVER fabricates any URL — the auth_url comes from the start_command response.
 */
export interface ExternalAuthPopupConfig {
  /** Command that starts the auth flow (e.g. "plex.auth.start") */
  start_command: string;
  /** Command that cancels the auth flow (e.g. "plex.auth.cancel") */
  cancel_command: string;
  /** SSE channel to listen for status updates */
  status_channel: string;
  /** Popup dimensions (width, height in px) */
  popup_size: { w: number; h: number };
}

/** Auth flow state machine (contract §7.2) */
export type AuthState = 'idle' | 'waiting' | 'success' | 'error' | 'timeout' | 'cancelled';

/** Response from the start_command (URL already validated master-side per §7.3) */
export interface StartCommandResponse {
  auth_url?: string;
  [key: string]: unknown;
}

/** Props for the external-auth-popup block (contract §7) */
export interface ExternalAuthPopupProps {
  /** Block context with API helpers */
  context: BlockContext;
  /** Block configuration */
  config: ExternalAuthPopupConfig;
  /** Optional title override (e.g. "Connexion au compte Plex") */
  title?: string;
}