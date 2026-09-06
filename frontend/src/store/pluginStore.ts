import { create } from 'zustand';
import { api } from '../hooks/useApi';
import {
  PLUGIN_PAGES_API_VERSION,
  type AdminPluginInfo,
  type PluginPageEntry,
  type PluginPagesResponse,
} from '../types/plugins';
import { logger } from '../lib/logger';

/**
 * Liste par défaut des plugins actifs — miroir exact du fallback de Sidebar.tsx
 * (ligne 29). Utilisée tant que `/api/admin/plugins` n'a pas répondu ou en cas
 * d'échec du fetch : les routes `/plugins/*` restent routables (fail-open
 * volontaire identique au comportement pré-migration). Les flags gate le
 * ROUTING uniquement, jamais l'état du registre backend.
 */
export const DEFAULT_ACTIVE_PLUGINS = ['systemd', 'docker', 'metrics', 'disk_analysis', 'clean_logs', 'plex'];

const REGISTRY_RESYNC_RETRY_MS = 500;

interface PluginState {
  pages: PluginPageEntry[];
  loading: boolean;
  error: string | null;
  apiVersion: number | null;
  activePluginIds: string[];
  fetchPluginPages: () => Promise<boolean>;
  fetchActivePlugins: () => Promise<boolean>;
  refreshRegistry: () => Promise<boolean>;
}

export const usePluginStore = create<PluginState>((set, get) => ({
  pages: [],
  loading: false,
  error: null,
  apiVersion: null,
  activePluginIds: DEFAULT_ACTIVE_PLUGINS,

  fetchPluginPages: async () => {
    set({ loading: true, error: null });
    try {
      const data = await api<PluginPagesResponse>('/api/plugins/pages');
      if (data && typeof data.version === 'number' && Array.isArray(data.pages)) {
        if (data.version > PLUGIN_PAGES_API_VERSION) {
          logger.warn(
            `Plugin API version mismatch: Server returned version ${data.version}, but client supports up to version ${PLUGIN_PAGES_API_VERSION}. Some pages may not render correctly.`
          );
        }
        set({
          pages: data.pages,
          apiVersion: data.version,
          error: null,
        });
      } else {
        // Fallback for older or unversioned APIs
        const rawPages = Array.isArray(data) ? data : [];
        set({
          pages: rawPages as PluginPageEntry[],
          apiVersion: 0,
          error: null,
        });
      }
      return true;
    } catch (err) {
      logger.error('Failed to fetch plugin pages:', err);
      set({ error: err instanceof Error ? err.message : 'Unknown error loading plugins' });
      return false;
    } finally {
      set({ loading: false });
    }
  },

  fetchActivePlugins: async () => {
    try {
      const response = await api<AdminPluginInfo[] | { plugins: AdminPluginInfo[] }>('/api/admin/plugins');
      const list = Array.isArray(response) ? response : (response?.plugins || []);
      const activeIds = list
        .filter((p) => Boolean(p.enabled && p.loaded))
        .map((p) => p.id);
      set({ activePluginIds: activeIds });
      return true;
    } catch (err) {
      // Échec → on garde la liste par défaut (fallback, miroir Sidebar) :
      // les routes restent routables, jamais de page blanche par flag inconnu.
      logger.error('Failed to fetch active plugins:', err);
      return false;
    }
  },

  refreshRegistry: async () => {
    const attemptSync = () =>
      Promise.allSettled([get().fetchPluginPages(), get().fetchActivePlugins()]);
    const isSynced = (results: PromiseSettledResult<boolean>[]) =>
      results.every((r) => r.status === 'fulfilled' && r.value === true);

    let results = await attemptSync();
    if (!isSynced(results)) {
      await new Promise((resolve) => setTimeout(resolve, REGISTRY_RESYNC_RETRY_MS));
      results = await attemptSync();
    }
    const synced = isSynced(results);
    if (!synced) {
      logger.error('Plugin registry resync failed after retry');
    }
    return synced;
  },
}));
