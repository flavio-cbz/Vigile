import { api } from '../hooks/useApi';
import { useToastStore } from '../store/useToastStore';
import { t as translate } from '../i18n';
import type { PluginAPI } from '../types/plugins';

export class RestrictedPluginAPI implements PluginAPI {
  readonly pluginId: string;
  readonly pluginName: string;
  readonly config: Readonly<Record<string, unknown>>;
  private readonly _navigate: (path: string) => void;

  constructor(
    pluginId: string,
    pluginName: string,
    config: Record<string, unknown>,
    navigate: (path: string) => void
  ) {
    this.pluginId = pluginId;
    this.pluginName = pluginName;
    this.config = Object.freeze({ ...config });
    this._navigate = navigate;
  }

  async fetch<T = unknown>(path: string, options?: RequestInit): Promise<T> {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    // Route format: /api/plugins/{plugin_id}/{path}
    const apiPath = `/api/plugins/${this.pluginId}${cleanPath}`;
    const res = await api<T>(apiPath, options);
    if (res === null) {
      throw new Error(`Empty response from plugin API: ${apiPath}`);
    }
    return res;
  }

  navigate(path: string): void {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    this._navigate(`/plugins/${this.pluginId}${cleanPath}`);
  }

  navigateGlobal(path: string): void {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    this._navigate(cleanPath);
  }

  t(key: string, params?: Record<string, string | number>): string {
    // Falls back to global t() translations helper
    return translate(key, params);
  }

  toast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): void {
    useToastStore.getState().addToast(type, message);
  }
}
