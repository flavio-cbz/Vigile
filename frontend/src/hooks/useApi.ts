import { useToastStore } from '../store/useToastStore';
import { useAuthStore } from '../store/authStore';
import { useLocaleStore } from '../store/localeStore';

export interface ApiOptions extends RequestInit {
  skipToast?: boolean;
  retries?: number;
}

export async function api<T = unknown>(
  url: string,
  options: ApiOptions = {},
): Promise<T | null> {
  const { skipToast = false, retries = 1, ...fetchOptions } = options;
  const token = useAuthStore.getState().accessToken;
  const locale = useLocaleStore.getState().locale;

  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string>),
  };
  headers['Accept-Language'] = locale;
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (
    !headers['Content-Type'] &&
    !(fetchOptions.body instanceof FormData)
  ) {
    headers['Content-Type'] = 'application/json';
  }

  let attempt = 0;
  const maxAttempts = retries + 1;

  while (attempt < maxAttempts) {
    try {
      attempt++;
      const response = await fetch(url, { ...fetchOptions, headers });

      if (response.status === 401) {
        useToastStore
          .getState()
          .addToast('error', 'Session expirée', 'Veuillez vous reconnecter.');
        useAuthStore.getState().logout();
        return null;
      }

      if (!response.ok) {
        if (response.status >= 500 && attempt < maxAttempts) {
          continue;
        }
        const errorText = await response
          .text()
          .catch(() => 'Erreur inconnue');
        throw new Error(errorText || `HTTP ${response.status}`);
      }

      // Handle 204 No Content
      if (response.status === 204) return null as T;

      return (await response.json()) as T;
    } catch (err) {
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 300 * attempt));
        continue;
      }
      if (!skipToast) {
        useToastStore.getState().addToast(
          'error',
          'Erreur réseau',
          err instanceof Error ? err.message : 'Requête échouée',
        );
      }
      throw err;
    }
  }
  return null;
}
