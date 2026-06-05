import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from './useApi';
import { useAuthStore } from '../store/authStore';

describe('api', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      accessToken: 'expired',
      refreshToken: 'refresh-1',
      user: { user_id: 'u1', username: 'demo', role: 'admin' },
      isAuthenticated: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('refreshes once and replays the original request after 401', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        access_token: 'access-2',
        refresh_token: 'refresh-2',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await api<{ ok: boolean }>('/api/nodes');

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/auth/refresh');
    expect(useAuthStore.getState().accessToken).toBe('access-2');
  });

  it('aborts requests after the configured timeout', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));

    const promise = api('/api/slow', { timeoutMs: 10, retries: 0, skipToast: true });
    // Attach handler before rejection to suppress Node.js unhandled rejection detection
    promise.catch(() => {});
    await vi.advanceTimersByTimeAsync(11);

    await expect(promise).rejects.toThrow('Request timed out');
    vi.useRealTimers();
  });
});
