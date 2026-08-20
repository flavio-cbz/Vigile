import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './useApi';
import { useAuthStore } from '../store/authStore';
import { logger } from '../lib/logger';

/**
 * Hook SWR first-party (J3b) résolvant la syntaxe `data:{command}` (contrat §3.5).
 *
 * Le BlockRenderer résout `data:{command}` en appelant ce hook, qui POSTe la
 * commande sur `/api/plugins/batch` (contrat §5.5, endpoint `master/api/plugins.py`)
 * et expose le résultat de la sous-requête correspondante.
 *
 * Sémantique stale-while-revalidate (S4) : les données en cache sont servies
 * immédiatement pendant qu'une revalidation s'exécute en arrière-plan.
 * Aucune dépendance externe — le pattern SWR minimal est réimplémenté ici.
 */

export interface BlockCommand {
  /** Nom de commande namespacé `<plugin_id>.<handler>` (registre §5.1). */
  command: string;
  /** Paramètres de la sous-requête (ex. `{ node_id }`). */
  params?: Record<string, unknown>;
}

export interface BlockDataOptions {
  /** Intervalle de revalidation stale-while-revalidate en ms (défaut 30_000). */
  revalidateInterval?: number;
  /** Paire de revision S4 `(boot_id, counter)` ; mismatch → résultat jeté. */
  revision?: { boot_id: string; counter: number } | null;
  /** Appelé quand le résultat est jeté pour mismatch de revision (S4). */
  onRevisionMismatch?: () => void;
  /** Signal d'annulation externe, transmis à `api` (convention AbortSignal). */
  signal?: AbortSignal | null;
}

/**
 * Événement SSE `plugins.invalidated` (T26, endpoint `/api/plugins/events/stream`).
 * Chaque invalidation porte la revision du plugin à l'émission, ce qui permet
 * au client de revalider avec `since` au lieu de purger son cache.
 */
export interface PluginInvalidationEvent {
  /** Plugin concerné par l'invalidation. */
  plugin_id: string;
  /** Identifiant de boot de l'engine (change à chaque redémarrage). */
  boot_id: string;
  /** Compteur de revision du plugin à l'émission de l'événement. */
  revision: number;
  /** Action d'origine (`updated`, `reloaded`, `unloaded`, ...). */
  action: string;
}

export interface UseBlockDataResult<T = unknown> {
  /** Données de la sous-requête (undefined tant que non chargées / jetées). */
  data: T | undefined;
  /** Erreur de la sous-requête (statut ≠ 200 ou échec réseau). */
  error: Error | null;
  /** `true` uniquement au premier chargement (SWR garde les données). */
  isLoading: boolean;
  /** `true` pendant qu'une revalidation est en vol. */
  isValidating: boolean;
  /** Revalidation manuelle. */
  mutate: () => Promise<void>;
}

// ── Cache SWR first-party, keyé par commande + params ──

interface CacheEntry {
  data: unknown;
  fetchedAt: number;
}

const cache = new Map<string, CacheEntry>();
const MAX_CACHE_ENTRIES = 200;

function setCacheEntry(key: string, entry: CacheEntry): void {
  // Éviction LRU / borne de taille pour éviter les fuites mémoire (H6)
  if (cache.size >= MAX_CACHE_ENTRIES && !cache.has(key)) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey !== undefined) {
      cache.delete(oldestKey);
    }
  }
  cache.set(key, entry);
}

const DEFAULT_REVALIDATE_INTERVAL_MS = 30_000;

/** Debounce des revalidations déclenchées par SSE (T26) : les événements en rafale fusionnent. */
const SSE_DEBOUNCE_MS = 500;

// ── Singleton de mutualisation SSE (C4) ──────────────────────────────────────
// Évite la saturation des connexions HTTP/1.1 du navigateur en partageant
// UNE seule connexion EventSource entre toutes les instances de useBlockData.

type InvalidationListener = (event: PluginInvalidationEvent) => void;

class PluginEventsManager {
  private es: EventSource | null = null;
  private token: string | null = null;
  private listeners = new Set<InvalidationListener>();
  private refCount = 0;

  subscribe(token: string, listener: InvalidationListener): () => void {
    this.listeners.add(listener);
    this.refCount++;

    if (!this.es || this.token !== token) {
      if (this.es) {
        this.es.close();
      }
      this.token = token;
      this.es = new EventSource(`/api/plugins/events/stream?token=${encodeURIComponent(token)}`);
      this.es.addEventListener('plugins.invalidated', (raw: Event) => {
        try {
          const event = JSON.parse((raw as MessageEvent).data) as PluginInvalidationEvent;
          for (const l of Array.from(this.listeners)) {
            l(event);
          }
        } catch {
          // ignore malformed SSE frames
        }
      });
      this.es.onerror = () => {
        logger.warn('SSE plugin events connection error, will retry');
      };
    }

    return () => {
      this.listeners.delete(listener);
      this.refCount--;
      if (this.refCount <= 0) {
        this.es?.close();
        this.es = null;
        this.token = null;
        this.refCount = 0;
      }
    };
  }
}

const pluginEventsManager = new PluginEventsManager();

/** Sérialisation stable : trie les clés d'objets récursivement (JSON.stringify). */
export function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/**
 * Clé de cache SWR : `command|params` sérialisés — deux jeux de params
 * différents (nœud A vs B, période 1h vs 7d) ne partagent jamais une entrée.
 */
export function stableCacheKey(command: BlockCommand): string {
  return `${command.command}|${stableStringify(command.params ?? {})}`;
}

interface BatchSubResult<T> {
  command: string;
  status: number;
  data?: T;
  error?: string;
}

/**
 * Réponse `/api/plugins/batch` (T26) : soit `{unchanged: true}` quand la
 * revision fournie via `since` est toujours d'actualité (le cache local reste
 * valide), soit la forme complète avec les résultats et la paire de revision
 * courante (absente si l'engine ne l'expose pas).
 */
type BatchResponse<T> =
  | { unchanged: true }
  | { results: BatchSubResult<T>[]; revision?: { boot_id: string; counter: number } };

/** S4 : deux revisions diffèrent si l'une manque ou si un champ de la paire change. */
function revisionsDiffer(
  captured: { boot_id: string; counter: number } | null | undefined,
  current: { boot_id: string; counter: number } | null | undefined,
): boolean {
  if (!captured) return false;
  if (!current) return true;
  return captured.boot_id !== current.boot_id || captured.counter !== current.counter;
}

export function useBlockData<T = unknown>(
  command: BlockCommand | null,
  options: BlockDataOptions = {},
): UseBlockDataResult<T> {
  const {
    revalidateInterval = DEFAULT_REVALIDATE_INTERVAL_MS,
    revision = null,
    onRevisionMismatch,
    signal,
  } = options;

  const [data, setData] = useState<T | undefined>(() => {
    if (!command) return undefined;
    const entry = cache.get(stableCacheKey(command));
    return entry ? (entry.data as T) : undefined;
  });
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(() => {
    if (!command) return false;
    return !cache.has(stableCacheKey(command));
  });
  const [isValidating, setIsValidating] = useState(false);

  // Refs stables : évitent de re-déclencher l'effet quand l'appelant passe des
  // objets frais à chaque rendu (command/options inline).
  const commandRef = useRef(command);
  const revisionRef = useRef(revision);
  const onMismatchRef = useRef(onRevisionMismatch);
  const signalRef = useRef(signal);
  const lastRevisionRef = useRef(revision);

  useEffect(() => {
    commandRef.current = command;
    revisionRef.current = revision;
    onMismatchRef.current = onRevisionMismatch;
    signalRef.current = signal;
    if (revision) lastRevisionRef.current = revision;
  });

  const pendingFlushRef = useRef<'since' | 'full' | null>(null);
  const flushTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const activeControllerRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async (since?: string): Promise<void> => {
    const cmd = commandRef.current;
    if (!cmd) return;

    // Une seule requête en vol à la fois : la précédente est annulée.
    activeControllerRef.current?.abort();
    const controller = new AbortController();
    activeControllerRef.current = controller;

    const onExternalAbort = () => controller.abort();
    const external = signalRef.current;
    if (external) {
      if (external.aborted) return;
      external.addEventListener('abort', onExternalAbort, { once: true });
    }

    // S4 : capture de la revision au début de requête.
    const capturedRevision = revisionRef.current;
    setIsValidating(true);

    try {
      // T26 : `since` (`<boot_id>:<counter>`) permet au serveur de répondre
      // `{unchanged: true}` quand aucune invalidation n'est survenue depuis.
      const body: Record<string, unknown> = {
        requests: [{ command: cmd.command, params: cmd.params ?? {} }],
      };
      if (since) body.since = since;

      const response = await api<BatchResponse<T>>('/api/plugins/batch', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!response) {
        throw new Error('réponse /batch vide');
      }

      // T26 : revision inchangée côté serveur → le cache local reste valide.
      if ('unchanged' in response) return;

      // S4 : mismatch de revision → résultat jeté, aucune écriture d'état.
      if (revisionsDiffer(capturedRevision, revisionRef.current)) {
        onMismatchRef.current?.();
        return;
      }

      // T26 : la paire renvoyée devient la dernière connue (base des `since` suivants).
      if (response.revision) lastRevisionRef.current = response.revision;

      const result = response.results.find((r) => r.command === cmd.command);
      if (!result) {
        throw new Error(`commande inconnue dans la réponse /batch : ${cmd.command}`);
      }
      if (result.status !== 200) {
        throw new Error(result.error ?? `commande ${cmd.command} : statut ${result.status}`);
      }

      setCacheEntry(stableCacheKey(cmd), { data: result.data, fetchedAt: Date.now() });
      setData(result.data);
      setError(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (external) external.removeEventListener('abort', onExternalAbort);
      const isCurrent = activeControllerRef.current === controller;
      if (isCurrent) activeControllerRef.current = null;
      // Pas d'écriture d'état après unmount/abort (StrictMode-safe).
      if (isCurrent && mountedRef.current) {
        setIsValidating(false);
        setIsLoading(false);
      }
    }
  }, []);

  // T26 : invalidation SSE debouncée. `full` (engine redémarré, plugin
  // déchargé) purge le cache et recharge ; `since` revalide avec la dernière
  // revision connue. En cas de rafale, `full` l'emporte sur `since`.
  const scheduleFlush = useCallback((kind: 'since' | 'full'): void => {
    pendingFlushRef.current = pendingFlushRef.current === 'full' || kind === 'full' ? 'full' : kind;
    if (flushTimerRef.current !== null) return;
    flushTimerRef.current = window.setTimeout(() => {
      flushTimerRef.current = null;
      const pending = pendingFlushRef.current;
      pendingFlushRef.current = null;
      const cmd = commandRef.current;
      if (!cmd || !mountedRef.current) return;

      if (pending === 'full') {
        cache.delete(stableCacheKey(cmd));
        setData(undefined);
        setError(null);
        setIsLoading(true);
        void fetchData();
        return;
      }
      const last = lastRevisionRef.current;
      void fetchData(last ? `${last.boot_id}:${last.counter}` : undefined);
    }, SSE_DEBOUNCE_MS);
  }, [fetchData]);

  // Marquage monté/démonté (StrictMode-safe : idempotent sous double-invoke).
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const commandKey = command ? stableCacheKey(command) : null;

  // Cycle de vie : fetch initial, revalidation périodique, reset sur changement
  // de commande, abort au démontage.
  useEffect(() => {
    const cmd = commandRef.current;
    if (!cmd) {
      setData(undefined);
      setError(null);
      setIsLoading(false);
      setIsValidating(false);
      return;
    }

    const entry = cache.get(stableCacheKey(cmd));
    const fresh = entry !== undefined && Date.now() - entry.fetchedAt < revalidateInterval;
    if (entry) {
      setData(entry.data as T);
      setError(null);
      setIsLoading(false);
    } else {
      setData(undefined);
      setError(null);
      setIsLoading(true);
    }

    if (!fresh) {
      void fetchData();
    }

    const timer = window.setInterval(() => {
      void fetchData();
    }, revalidateInterval);

    return () => {
      window.clearInterval(timer);
      activeControllerRef.current?.abort();
    };
  }, [commandKey, revalidateInterval, fetchData]);

  // T26 : souscription SSE aux invalidations de plugin. Un événement perturbe
  // la dernière revision connue et déclenche une revalidation `since`
  // debouncée — ou une invalidation totale si l'engine a redémarré (boot_id
  // inconnu) ou si le plugin a été déchargé.
  const accessToken = useAuthStore((s) => s.accessToken);
  useEffect(() => {
    const cmd = commandRef.current;
    if (!cmd || !accessToken) return;

    const pluginId = cmd.command.split('.')[0];

    const onInvalidation = (event: PluginInvalidationEvent) => {
      const last = lastRevisionRef.current;
      // Fail-safe : boot_id inconnu = engine redémarré → cache entier périmé.
      if (last && event.boot_id !== last.boot_id) {
        scheduleFlush('full');
        return;
      }
      if (event.plugin_id !== pluginId) return;
      if (event.action === 'unloaded') {
        scheduleFlush('full');
        return;
      }
      if (!last || event.revision > last.counter) {
        scheduleFlush('since');
      }
    };

    const unsubscribe = pluginEventsManager.subscribe(accessToken, onInvalidation);

    return () => {
      unsubscribe();
      if (flushTimerRef.current !== null) {
        window.clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      pendingFlushRef.current = null;
    };
  }, [commandKey, accessToken, scheduleFlush]);

  const mutate = useCallback(async (): Promise<void> => {
    await fetchData();
  }, [fetchData]);

  return { data, error, isLoading, isValidating, mutate };
}