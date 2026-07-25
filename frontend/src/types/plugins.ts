/**
 * Vigile Plugin Frontend Types & Interfaces
 * Versioned under API Version 1.
 */

export const PLUGIN_PAGES_API_VERSION = 1;

export interface PluginPageEntry {
  plugin_id: string;
  id: string;
  page_id?: string; // Keep as optional for backward compatibility if needed
  title: string;
  icon: string | null;
  sidebar: boolean;
  component: string;     // Nom du composant React (ex: "DockerContainers")
  route: string;          // Route frontend (ex: "/plugins/docker/containers")
  roles: string[];
  params: string[];
}

export interface PluginPagesResponse {
  version: number;
  pages: PluginPageEntry[];
}

export interface PluginAPI {
  /** Fetch call automatically prefixed to /api/plugins/<id>/ */
  fetch<T = unknown>(path: string, options?: RequestInit): Promise<T>;
  
  /** Plugin configuration loaded from settings (read-only) */
  readonly config: Readonly<Record<string, unknown>>;
  
  /** Identifiers */
  readonly pluginId: string;
  readonly pluginName: string;
  
  /** Navigation relative to the plugin route namespace */
  navigate(path: string): void;
  
  /** Navigation absolute to the entire Vigile app */
  navigateGlobal(path: string): void;
  
  /** SCOPED translation helper */
  t(key: string, params?: Record<string, string>): string;
  
  /** Display notification toasts */
  toast(message: string, type?: 'success' | 'error' | 'warning' | 'info'): void;
}
