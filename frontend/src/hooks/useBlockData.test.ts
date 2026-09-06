import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useBlockData, stableCacheKey } from './useBlockData';
import { api } from './useApi';
import { useAuthStore } from '../store/authStore';

vi.mock('./useApi', () => ({
  api: vi.fn(),
}));

const apiMock = vi.mocked(api);

/** EventSource factice structurellement compatible (T26) : capture les
 * instances créées par le hook et permet d'émettre des événements de test. */
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  readyState = 0;
  withCredentials = false;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, Array<(ev: Event) => void>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (ev: Event) => void): void {
    const list = this.listeners.get(type) ?? [];
    list.push(listener);
    this.listeners.set(type, list);
  }

  removeEventListener(type: string, listener: (ev: Event) => void): void {
    const list = this.listeners.get(type) ?? [];
    this.listeners.set(type, list.filter((l) => l !== listener));
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

function getLastEventSource(): MockEventSource | undefined {
  return MockEventSource.instances[MockEventSource.instances.length - 1];
}

describe('useBlockData', () => {
  afterEach(() => {
    apiMock.mockReset();
  });

  it('fetches batch and returns data for the requested command', async () => {
    apiMock.mockResolvedValue({
      results: [{ command: 'systemd.read_logs', status: 200, data: { lines: ['a', 'b'] } }],
    });

    const { result } = renderHook(() => useBlockData({ command: 'systemd.read_logs' }));

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual({ lines: ['a', 'b'] }));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isValidating).toBe(false);
    expect(result.current.fetchedAt).toBeTypeOf('number');
    expect(apiMock).toHaveBeenCalledWith(
      '/api/plugins/batch',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ requests: [{ command: 'systemd.read_logs', params: {} }] }),
      }),
    );
  });

  it('null command returns no fetch', () => {
    const { result } = renderHook(() => useBlockData(null));

    expect(result.current.data).toBeUndefined();
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isValidating).toBe(false);
    expect(result.current.fetchedAt).toBeNull();
    expect(apiMock).not.toHaveBeenCalled();
  });

  it('sub-request error status throws', async () => {
    apiMock.mockResolvedValue({
      results: [
        { command: 'docker.containers', status: 403, error: 'permission denied for command: docker.containers' },
      ],
    });

    const { result } = renderHook(() => useBlockData({ command: 'docker.containers' }));

    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    expect(result.current.error?.message).toContain('permission denied');
    expect(result.current.data).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
  });

  it('aborts on unmount', async () => {
    const abortSpy = vi.fn();
    apiMock.mockImplementation((_url, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => {
        abortSpy();
        reject(new DOMException('Aborted', 'AbortError'));
      });
    }));

    const { unmount } = renderHook(() => useBlockData({ command: 'plex.sessions' }));

    expect(apiMock).toHaveBeenCalledWith(
      '/api/plugins/batch',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    unmount();
    expect(abortSpy).toHaveBeenCalled();
    // Aucune écriture d'état après unmount : pas de warning act, pas de throw.
    await act(async () => {});
  });

  it('revision mismatch discards result', async () => {
    const onMismatch = vi.fn();
    let resolveFetch!: (value: unknown) => void;
    apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolveFetch = resolve; }));

    const { result, rerender } = renderHook(
      ({ revision }) => useBlockData({ command: 'plex.stats' }, { revision, onRevisionMismatch: onMismatch }),
      { initialProps: { revision: { boot_id: 'A', counter: 1 } } },
    );

    // La requête part avec la revision A capturée ; le hook est re-rendu avec B.
    rerender({ revision: { boot_id: 'B', counter: 1 } });

    await act(async () => {
      resolveFetch({ results: [{ command: 'plex.stats', status: 200, data: { users: 3 } }] });
    });

    expect(result.current.data).toBeUndefined();
    expect(onMismatch).toHaveBeenCalledTimes(1);
  });

  it('stale-while-revalidate keeps data during revalidation', async () => {
    apiMock.mockResolvedValueOnce({
      results: [{ command: 'systemd.services', status: 200, data: { services: ['ssh'] } }],
    });

    const { result } = renderHook(() => useBlockData({ command: 'systemd.services' }));
    await waitFor(() => expect(result.current.data).toEqual({ services: ['ssh'] }));

    let resolveSecond!: (value: unknown) => void;
    apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));

    let mutatePromise!: Promise<void>;
    act(() => {
      mutatePromise = result.current.mutate();
    });

    // Revalidation en vol : les données périmées restent servies.
    expect(result.current.isValidating).toBe(true);
    expect(result.current.data).toEqual({ services: ['ssh'] });

    await act(async () => {
      resolveSecond({ results: [{ command: 'systemd.services', status: 200, data: { services: ['ssh', 'nginx'] } }] });
      await mutatePromise;
    });

    expect(result.current.data).toEqual({ services: ['ssh', 'nginx'] });
    expect(result.current.isValidating).toBe(false);
  });

  it('cache key differs for same command with different params', () => {
    const nodeA = stableCacheKey({
      command: 'metrics.get_metrics_history',
      params: { node_id: 'n1', period: '1h' },
    });
    const nodeB = stableCacheKey({
      command: 'metrics.get_metrics_history',
      params: { node_id: 'n2', period: '1h' },
    });
    const period7d = stableCacheKey({
      command: 'metrics.get_metrics_history',
      params: { node_id: 'n1', period: '7d' },
    });
    expect(nodeA).not.toBe(nodeB);
    expect(nodeA).not.toBe(period7d);
    // L'ordre des clés d'objet ne change pas la clé (sérialisation stable).
    const reordered = stableCacheKey({
      command: 'metrics.get_metrics_history',
      params: { period: '1h', node_id: 'n1' },
    });
    expect(reordered).toBe(nodeA);
  });

  it('params change triggers a refetch and serves the new entry', async () => {
    // Deux réponses distinctes : la valeur 2 ne peut provenir que du second fetch,
    // ce qui rend l'assertion finale déterministe (pas de race sur l'état data).
    apiMock
      .mockResolvedValueOnce({
        results: [
          { command: 'metrics.get_metrics_history', status: 200, data: { history: [{ cpu: 1 }], count: 1 } },
        ],
      })
      .mockResolvedValueOnce({
        results: [
          { command: 'metrics.get_metrics_history', status: 200, data: { history: [{ cpu: 1 }, { cpu: 2 }], count: 2 } },
        ],
      });

    const { result, rerender } = renderHook(
      ({ params }) => useBlockData({ command: 'metrics.get_metrics_history', params }),
      { initialProps: { params: { node_id: 'n1', period: '24h' } } },
    );

    await waitFor(() => expect(result.current.data).toEqual({ history: [{ cpu: 1 }], count: 1 }));
    expect(apiMock).toHaveBeenCalledTimes(1);

    // Changement de params → nouvelle clé de cache → refetch avec le nouveau body.
    rerender({ params: { node_id: 'n1', period: '7d' } });
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    const lastCall = apiMock.mock.calls[1];
    expect(JSON.parse(String(lastCall[1]?.body))).toEqual({
      requests: [{ command: 'metrics.get_metrics_history', params: { node_id: 'n1', period: '7d' } }],
    });
    await waitFor(() => expect(result.current.data).toEqual({ history: [{ cpu: 1 }, { cpu: 2 }], count: 2 }));
  });

  describe('invalidation SSE (T26)', () => {
    beforeEach(() => {
      MockEventSource.instances = [];
      vi.stubGlobal('EventSource', MockEventSource);
      useAuthStore.setState({ accessToken: 'test-token' });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
      useAuthStore.setState({ accessToken: null });
    });

    it('revalide avec `since` quand un événement du plugin a une revision supérieure', async () => {
      apiMock
        .mockResolvedValueOnce({
          results: [{ command: 'systemd.status', status: 200, data: { lines: ['a'] } }],
          revision: { boot_id: 'b1', counter: 1 },
        })
        .mockResolvedValueOnce({
          results: [{ command: 'systemd.status', status: 200, data: { lines: ['a', 'b'] } }],
          revision: { boot_id: 'b1', counter: 2 },
        });

      const { result } = renderHook(() => useBlockData({ command: 'systemd.status' }));
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['a'] }));

      const es = getLastEventSource();
      expect(es).toBeDefined();
      expect(es?.url).toBe('/api/plugins/events/stream?token=test-token');

      act(() => {
        es?.emit('plugins.invalidated', {
          plugin_id: 'systemd',
          boot_id: 'b1',
          revision: 2,
          action: 'updated',
        });
      });

      await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2), { timeout: 3000 });
      const lastCall = apiMock.mock.calls[1];
      expect(JSON.parse(String(lastCall[1]?.body))).toEqual({
        requests: [{ command: 'systemd.status', params: {} }],
        since: 'b1:1',
      });
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['a', 'b'] }));
    });

    it('réponse `{unchanged: true}` : cache conservé, aucune remise à zéro', async () => {
      apiMock
        .mockResolvedValueOnce({
          results: [{ command: 'systemd.unit', status: 200, data: { lines: ['a'] } }],
          revision: { boot_id: 'b1', counter: 1 },
        })
        .mockResolvedValueOnce({ unchanged: true });

      const { result } = renderHook(() => useBlockData({ command: 'systemd.unit' }));
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['a'] }));

      act(() => {
        getLastEventSource()?.emit('plugins.invalidated', {
          plugin_id: 'systemd',
          boot_id: 'b1',
          revision: 2,
          action: 'updated',
        });
      });

      await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2), { timeout: 3000 });
      expect(result.current.data).toEqual({ lines: ['a'] });
      expect(result.current.error).toBeNull();
      expect(result.current.isLoading).toBe(false);
    });

    it('ignore les événements des autres plugins', async () => {
      apiMock.mockResolvedValueOnce({
        results: [{ command: 'plex.media', status: 200, data: { lines: ['a'] } }],
        revision: { boot_id: 'b1', counter: 1 },
      });

      const { result } = renderHook(() => useBlockData({ command: 'plex.media' }));
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['a'] }));
      expect(apiMock).toHaveBeenCalledTimes(1);

      act(() => {
        getLastEventSource()?.emit('plugins.invalidated', {
          plugin_id: 'systemd',
          boot_id: 'b1',
          revision: 5,
          action: 'updated',
        });
      });

      await new Promise((resolve) => window.setTimeout(resolve, 600));
      expect(apiMock).toHaveBeenCalledTimes(1);
    });

    it('boot_id différent → invalidation totale : cache purgé + rechargement', async () => {
      apiMock.mockResolvedValueOnce({
        results: [{ command: 'plex.library', status: 200, data: { lines: ['a'] } }],
        revision: { boot_id: 'b1', counter: 1 },
      });
      let resolveSecond!: (value: unknown) => void;
      apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));

      const { result } = renderHook(() => useBlockData({ command: 'plex.library' }));
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['a'] }));

      // Événement d'un AUTRE plugin mais avec un boot_id inconnu : fail-safe → purge totale.
      act(() => {
        getLastEventSource()?.emit('plugins.invalidated', {
          plugin_id: 'plex',
          boot_id: 'b2',
          revision: 3,
          action: 'updated',
        });
      });

      await waitFor(() => {
        expect(apiMock).toHaveBeenCalledTimes(2);
        expect(result.current.data).toBeUndefined();
      }, { timeout: 3000 });
      expect(result.current.isLoading).toBe(true);
      const lastCall = apiMock.mock.calls[1];
      expect(JSON.parse(String(lastCall[1]?.body))).toEqual({
        requests: [{ command: 'plex.library', params: {} }],
      });

      await act(async () => {
        resolveSecond({
          results: [{ command: 'plex.library', status: 200, data: { lines: ['fresh'] } }],
          revision: { boot_id: 'b2', counter: 0 },
        });
      });
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['fresh'] }));
    });

    it('fusionne les événements en rafale en une seule revalidation (debounce)', async () => {
      apiMock
        .mockResolvedValueOnce({
          results: [{ command: 'docker.networks', status: 200, data: { lines: ['a'] } }],
          revision: { boot_id: 'b1', counter: 1 },
        })
        .mockResolvedValueOnce({
          results: [{ command: 'docker.networks', status: 200, data: { lines: ['a', 'b', 'c'] } }],
          revision: { boot_id: 'b1', counter: 5 },
        });

      const { result } = renderHook(() => useBlockData({ command: 'docker.networks' }));
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['a'] }));

      const es = getLastEventSource();
      act(() => {
        es?.emit('plugins.invalidated', { plugin_id: 'docker', boot_id: 'b1', revision: 2, action: 'updated' });
        es?.emit('plugins.invalidated', { plugin_id: 'docker', boot_id: 'b1', revision: 3, action: 'updated' });
        es?.emit('plugins.invalidated', { plugin_id: 'docker', boot_id: 'b1', revision: 4, action: 'updated' });
      });

      await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2), { timeout: 3000 });
      await waitFor(() => expect(result.current.data).toEqual({ lines: ['a', 'b', 'c'] }));
      expect(apiMock).toHaveBeenCalledTimes(2);
    });

    it('ferme la connexion SSE au démontage et n\'exécute aucun flush', async () => {
      apiMock.mockResolvedValueOnce({
        results: [{ command: 'systemd.journal', status: 200, data: { lines: ['a'] } }],
        revision: { boot_id: 'b1', counter: 1 },
      });

      const { unmount } = renderHook(() => useBlockData({ command: 'systemd.journal' }));
      await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));

      const es = getLastEventSource();
      expect(es?.closed).toBe(false);

      unmount();
      expect(es?.closed).toBe(true);

      act(() => {
        es?.emit('plugins.invalidated', { plugin_id: 'systemd', boot_id: 'b1', revision: 9, action: 'updated' });
      });
      await new Promise((resolve) => window.setTimeout(resolve, 600));
      expect(apiMock).toHaveBeenCalledTimes(1);
    });
  });
});