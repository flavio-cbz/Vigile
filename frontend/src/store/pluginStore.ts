import { create } from 'zustand';
import { api } from '../hooks/useApi';
import {
  PLUGIN_PAGES_API_VERSION,
  type PluginPageEntry,
  type PluginPagesResponse,
} from '../types/plugins';
import { logger } from '../lib/logger';

interface PluginState {
  pages: PluginPageEntry[];
  loading: boolean;
  error: string | null;
  apiVersion: number | null;
  fetchPluginPages: () => Promise<void>;
}

export const usePluginStore = create<PluginState>((set) => ({
  pages: [],
  loading: false,
  error: null,
  apiVersion: null,

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
    } catch (err) {
      logger.error('Failed to fetch plugin pages:', err);
      set({ error: err instanceof Error ? err.message : 'Unknown error loading plugins' });
    } finally {
      set({ loading: false });
    }
  },
}));
