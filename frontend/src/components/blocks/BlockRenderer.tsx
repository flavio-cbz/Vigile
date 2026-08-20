import React, { Suspense, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router';
import { AlertCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { t as translate } from '../../i18n';
import { useAuthStore } from '../../store/authStore';
import { useNodeStore } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';
import { ErrorBoundary } from './ErrorBoundary';
import { getBlockComponent } from './registry';
import type {
  BlockAPI,
  BlockConfig,
  BlockContext,
  BlockState,
} from './types';

// ── Restricted API mirror (contract §3.3) ───────────────────────────────────

function buildBlockApi(
  pluginId: string,
  navigate: (path: string) => void,
  pluginConfig: Record<string, unknown>
): BlockAPI {
  const clean = (path: string) => (path.startsWith('/') ? path : `/${path}`);
  return {
    config: Object.freeze({ ...pluginConfig }),
    async fetch<T = unknown>(path: string, options?: RequestInit): Promise<T> {
      const apiPath = `/api/plugins/${pluginId}${clean(path)}`;
      const res = await api<T>(apiPath, options);
      if (res === null) {
        throw new Error(`Empty response from plugin API: ${apiPath}`);
      }
      return res;
    },
    navigate(path: string): void {
      navigate(`/plugins/${pluginId}${clean(path)}`);
    },
    navigateGlobal(path: string): void {
      navigate(clean(path));
    },
    t(key: string, params?: Record<string, string | number>): string {
      return translate(key, params);
    },
    toast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): void {
      useToastStore.getState().addToast(type, message);
    },
  };
}

// ── subscribeStatus: channel → SSE EventSource (contract §7.4) ─────────────
// Convention: channel "plex.auth.status" → GET /api/plugins/plex/auth/status/stream?token=<jwt>
// Mapping: strip plugin prefix → dots become slashes → append /stream

function buildSubscribeStatus(
  pluginId: string,
): (
  channel: string,
  cb: (data: Record<string, unknown>) => void,
) => () => void {
  return (channel: string, cb: (data: Record<string, unknown>) => void): (() => void) => {
    // Channel must start with "<pluginId>." to be resolvable
    if (!channel.startsWith(`${pluginId}.`)) {
      return () => {}; // no-op unsubscribe for unresolvable channels
    }

    const suffix = channel.slice(pluginId.length + 1); // e.g. "auth.status"
    const pathSuffix = suffix.split('.').join('/'); // e.g. "auth/status"
    const sseUrl = `/api/plugins/${pluginId}/${pathSuffix}/stream`;

    let es: EventSource | null = null;
    let closed = false;

    const subscribe = () => {
      // Auth token from Zustand store (EventSource cannot send headers)
      const token = useAuthStore.getState().accessToken;
      const url = token ? `${sseUrl}?token=${encodeURIComponent(token)}` : sseUrl;

      const source = new EventSource(url);
      es = source;

      source.onmessage = (ev: MessageEvent) => {
        if (closed) return;
        try {
          const parsed = JSON.parse(ev.data) as Record<string, unknown>;
          cb(parsed);
        } catch {
          // ignore partial/malformed SSE frames
        }
      };

      source.onerror = () => {
        // EventSource natif gère la reconnexion automatique avec backoff.
        // Ne pas appeler source.close() pour préserver la résilience réseau (H5).
      };
    };

    subscribe();

    return () => {
      closed = true;
      es?.close();
      es = null;
    };
  };
}

// ── State-variant shells (contract §2) ──────────────────────────────────────

function BusySpinner() {
  return (
    <div data-testid="block-busy" className="flex items-center justify-center py-8">
      <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-orange-500 border-zinc-800" />
    </div>
  );
}

function IdlePlaceholder() {
  return (
    <div
      data-testid="block-idle"
      className="animate-pulse rounded-xl bg-zinc-800/60 h-24"
    />
  );
}

function EmptyCard({ message }: { message?: string }) {
  return (
    <div
      data-testid="block-empty"
      className="flex flex-col items-center justify-center text-center p-6 gap-2 bg-zinc-900/40 rounded-xl border border-zinc-800"
    >
      <AlertCircle className="w-6 h-6 text-zinc-500" />
      <p className="text-sm text-zinc-400">{message ?? 'Aucune donnée disponible'}</p>
    </div>
  );
}

function ErrorCard({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div
      data-testid="block-error"
      className="card border-danger/20 p-6 flex flex-col items-center text-center gap-3"
    >
      <AlertTriangle className="w-8 h-8 text-danger" />
      <div>
        <p className="text-sm font-semibold text-ink-primary">
          {translate('error_boundary.title')}
        </p>
        <p className="text-xs text-ink-secondary mt-1">
          {message || translate('error_boundary.description')}
        </p>
      </div>
      {onRetry && (
        <button onClick={onRetry} className="btn btn-secondary text-xs py-1 px-3">
          <RefreshCw className="w-3.5 h-3.5" />
          {translate('error_boundary.retry')}
        </button>
      )}
    </div>
  );
}

// ── Variant dispatch (contract §2.1) ────────────────────────────────────────

function renderBlock(
  block: BlockConfig,
  context: BlockContext,
  state: BlockState,
  data: unknown,
  error: Error | null,
  onRetry: (() => void) | undefined
): React.ReactNode {
  switch (state) {
    case 'busy':
      return <BusySpinner />;
    case 'error':
      return <ErrorCard message={error?.message} onRetry={onRetry} />;
    case 'empty':
      return <EmptyCard message={block.emptyMessage} />;
    case 'idle':
      return <IdlePlaceholder />;
    case 'data': {
      const Component = getBlockComponent(block.type);
      if (!Component) {
        return <ErrorCard message={`Type de bloc inconnu : ${block.type}`} onRetry={onRetry} />;
      }
      return (
        <Component
          context={context}
          config={block}
          state={state}
          data={data}
          error={error}
          onRetry={onRetry}
        />
      );
    }
    default:
      return <ErrorCard message={`État de bloc inconnu : ${state}`} onRetry={onRetry} />;
  }
}

// ── Renderer ────────────────────────────────────────────────────────────────

export interface BlockRendererProps {
  /** Plugin id used to prefix API and navigation paths. */
  pluginId: string;
  /** Declarative block definitions (MetaSchemaV2-derived). */
  blocks: BlockConfig[];
  /** Per-block runtime state, keyed by block id (defaults to 'idle'). */
  states?: Record<string, BlockState>;
  /** Per-block data payload, keyed by block id. */
  data?: Record<string, unknown>;
  /** Per-block error, keyed by block id (used when state === 'error'). */
  errors?: Record<string, Error | null>;
  /** Retry callback, keyed by block id. */
  onRetry?: (blockId: string) => void;
  /** Plugin configuration (read-only, Object.freeze). */
  pluginConfig?: Record<string, unknown>;
}

/**
 * BlockRenderer skeleton (J2-T7): builds the BlockContext per contract §3 and
 * dispatches each block definition on `config.type` against the registry,
 * rendering the five state variants (idle/busy/error/empty/data) per §2.
 * Every block is wrapped in a per-block ErrorBoundary (§2.4) — a failing block
 * never blanks the page.
 */
export const BlockRenderer: React.FC<BlockRendererProps> = ({
  pluginId,
  blocks,
  states,
  data: dataMap,
  errors,
  onRetry,
  pluginConfig = {},
}) => {
  const navigate = useNavigate();
  const params = useParams() as Record<string, string>;
  // Contract §3.2: the renderer reads the store, never the block code.
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const { user } = useAuthStore();
  const roles = [user?.role ?? 'viewer'];

  const api = useMemo(
    () => buildBlockApi(pluginId, navigate, pluginConfig),
    [pluginId, navigate, pluginConfig]
  );

  const subscribeStatus = useMemo(
    () => buildSubscribeStatus(pluginId),
    [pluginId],
  );

  return (
    <div className="flex flex-col gap-4">
      {blocks.map((block) => {
        const state = states?.[block.id] ?? 'idle';
        const blockData = dataMap?.[block.id];
        const error = errors?.[block.id] ?? null;
        const retry = onRetry ? () => onRetry(block.id) : undefined;

        const context: BlockContext = {
          params,
          node_id:
            block.needs?.includes('node_id') && selectedNodeId && selectedNodeId !== 'all'
              ? selectedNodeId
              : undefined,
          navigate: api.navigate,
          navigateGlobal: api.navigateGlobal,
          config: Object.freeze({ ...(block.config ?? {}) }),
          toast: api.toast,
          t: api.t,
          roles,
          api,
          subscribeStatus,
        };

        return (
          <ErrorBoundary key={block.id} onRetry={retry}>
            <Suspense fallback={<BusySpinner />}>
              {renderBlock(block, context, state, blockData, error, retry)}
            </Suspense>
          </ErrorBoundary>
        );
      })}
    </div>
  );
};