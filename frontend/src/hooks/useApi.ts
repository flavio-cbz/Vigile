import { useToastStore } from '../store/useToastStore';
import { useAuthStore } from '../store/authStore';
import { useLocaleStore } from '../store/localeStore';
import { t } from '../i18n';

const toastedErrors = new WeakSet<object>();

export class HttpError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

/** Cooldown to prevent toast floods when the rate-limiter rejects many requests in a row. */
let lastRateLimitToastTime = 0;
const RATE_LIMIT_TOAST_COOLDOWN_MS = 6000;

export interface ApiOptions extends RequestInit {
  skipToast?: boolean;
  retries?: number;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 15000;
let refreshPromise: Promise<boolean> | null = null;

function withTimeout(timeoutMs: number, signal?: AbortSignal | null): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  if (signal) {
    signal.addEventListener('abort', onAbort, { once: true });
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      window.clearTimeout(timeout);
      if (signal) {
        signal.removeEventListener('abort', onAbort);
      }
    },
  };
}

async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const { refreshToken, setTokens, logout } = useAuthStore.getState();
    const body = refreshToken ? { refresh_token: refreshToken } : {};

    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        logout();
        return false;
      }

      const data = await response.json() as { access_token?: string; refresh_token?: string };
      setTokens(data.access_token ?? null, data.refresh_token ?? null);
      return true;
    } catch {
      logout();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function api<T = unknown>(
  url: string,
  options: ApiOptions = {},
): Promise<T | null> {
  const { skipToast = false, retries = 1, timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;
  const locale = useLocaleStore.getState().locale;
  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string>),
    'Accept-Language': locale,
  };

  const contentTypeKey = Object.keys(headers).find(
    (k) => k.toLowerCase() === 'content-type'
  );
  if (contentTypeKey) {
    if (contentTypeKey !== 'Content-Type') {
      headers['Content-Type'] = headers[contentTypeKey];
      delete headers[contentTypeKey];
    }
  } else if (!(fetchOptions.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  let attempt = 0;
  let refreshed = false;
  const maxAttempts = retries + 1;

  while (attempt < maxAttempts) {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else {
      delete headers.Authorization;
    }

    const timeout = withTimeout(timeoutMs, fetchOptions.signal);
    try {
      attempt++;
      const response = await fetch(url, {
        ...fetchOptions,
        credentials: fetchOptions.credentials ?? 'include',
        headers,
        signal: timeout.signal,
      });

      if (
        response.status === 401 &&
        !refreshed &&
        !url.includes('/api/auth/login') &&
        !url.includes('/api/auth/refresh')
      ) {
        refreshed = true;
        timeout.cleanup();
        if (await refreshSession()) {
          continue;
        }
        useToastStore
          .getState()
          .addToast('error', t('api.toast.session_expired'), t('api.toast.session_expired_msg'));
        return null;
      }

      if (!response.ok) {
        if (response.status === 429) {
          // Rate-limited request — deduplicate toasts with a cooldown to prevent notification floods
          const errorText = await response.text().catch(() => t('common.error_unknown'));
          let displayMessage = t('api.toast.rate_limit');
          try {
            const parsed = JSON.parse(errorText);
            if (parsed && typeof parsed === 'object') {
              displayMessage = parsed.detail || parsed.error || displayMessage;
            }
          } catch {
            // empty
          }
          if (!skipToast) {
            const now = Date.now();
            if (now - lastRateLimitToastTime > RATE_LIMIT_TOAST_COOLDOWN_MS) {
              lastRateLimitToastTime = now;
              useToastStore.getState().addToast('warning', t('api.toast.rate_limit_title'), displayMessage);
            }
          }
          const error = new HttpError(displayMessage, 429);
          toastedErrors.add(error);
          throw error;
        }
        if (response.status >= 500 && attempt < maxAttempts) {
          continue;
        }
        const errorText = await response.text().catch(() => t('common.error_unknown'));
        let displayMessage = errorText;
        try {
          const parsed = JSON.parse(errorText);
          if (parsed && typeof parsed === 'object') {
            if (Array.isArray(parsed.detail)) {
              displayMessage = parsed.detail
                .map((d: any) => (typeof d === 'object' && d ? d.msg || JSON.stringify(d) : String(d)))
                .join(', ');
            } else if (typeof parsed.detail === 'object' && parsed.detail !== null) {
              displayMessage = JSON.stringify(parsed.detail);
            } else {
              displayMessage = parsed.detail || parsed.message || parsed.error || errorText;
            }
          }
        } catch {
          // ignore parse error, use plain text
        }
        const error = new HttpError(typeof displayMessage === 'string' ? displayMessage : JSON.stringify(displayMessage) || `HTTP ${response.status}`, response.status);
        if (response.status >= 500 && !skipToast) {
          useToastStore.getState().addToast('error', t('api.toast.server_error'), displayMessage || `HTTP ${response.status}`);
          toastedErrors.add(error);
        }
        throw error;
      }

      if (response.status === 204) return null as T;

      return (await response.json()) as T;
    } catch (err) {
      if (err instanceof HttpError && err.status < 500) {
        throw err;
      }

      const normalizedError =
        err instanceof DOMException && err.name === 'AbortError'
          ? new Error('Request timed out')
          : err;

      if (attempt < maxAttempts) {
        await new Promise((resolve) => window.setTimeout(resolve, 300 * attempt));
        continue;
      }
      if (!skipToast && !(normalizedError instanceof Error && toastedErrors.has(normalizedError))) {
        useToastStore.getState().addToast(
          'error',
          'Erreur réseau',
          normalizedError instanceof Error ? normalizedError.message : 'Requête échouée',
        );
      }
      throw normalizedError;
    } finally {
      timeout.cleanup();
    }
  }

  return null;
}
