import { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router';
import { api } from './useApi';
import { useAuthStore } from '../store/authStore';
import { usePermission } from './usePermission';
import { useToastStore } from '../store/useToastStore';
import { usePluginStore } from '../store/pluginStore';
import { useLocale } from '../i18n';
import { logger } from '../lib/logger';

export interface PluginInfo {
  id: string;
  name: string;
  path: string;
  module: string;
  loaded: boolean;
  hooks: string[];
  error?: string;
  version?: string;
  description?: string;
  config?: Record<string, unknown>;
  schema?: Record<
    string,
    {
      type: string;
      title: string;
      default?: unknown;
      description?: string;
      enum?: string[];
    }
  >;
}

export interface PluginListResponse {
  loaded_plugins: string[];
  plugins: PluginInfo[];
}

export interface RegistryPlugin {
  id: string;
  name: string;
  description: string;
  author: string;
  version: string;
  download_url: string;
}

export const usePluginsData = () => {
  const { t } = useLocale();
  const { isAdmin } = usePermission();
  const addToast = useToastStore((s) => s.addToast);
  const location = useLocation();

  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loadedNames, setLoadedNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeTab, setActiveTab] = useState<'installed' | 'registry'>('installed');
  const [registryPlugins, setRegistryPlugins] = useState<RegistryPlugin[]>([]);
  const [loadingRegistry, setLoadingRegistry] = useState(false);
  const [installingPlugin, setInstallingPlugin] = useState<string | null>(null);
  const [selectedPlugin, setSelectedPlugin] = useState<PluginInfo | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const openPluginId = params.get('open');
    if (openPluginId && plugins.length > 0) {
      const target = plugins.find(p => p.id === openPluginId);
      if (target) {
        setSelectedPlugin({ ...target, loaded: loadedNames.includes(target.id) });
      }
    }
  }, [location.search, plugins, loadedNames]);

  const closeDetailsModal = () => {
    setSelectedPlugin(null);
  };

  const fetchPlugins = async () => {
    setLoading(true);
    try {
      const data = await api<PluginListResponse>('/api/admin/plugins');
      if (data) {
        setPlugins(data.plugins || []);
        setLoadedNames(data.loaded_plugins || []);
      }
    } catch (err) {
      logger.error('Failed to fetch plugins:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async (pluginId: string, configData: Record<string, unknown>) => {
    try {
      await api(`/api/admin/plugins/${pluginId}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configData),
      });
      addToast('success', t('plugins.config_saved') || 'Configuration enregistrée', `La configuration du plugin ${pluginId} a été mise à jour.`);
      await fetchPlugins();
      setSelectedPlugin(prev => prev ? { ...prev, config: configData } : null);
    } catch (err) {
      logger.error('Failed to save configuration:', err);
      addToast('error', t('plugins.config_failed') || 'Erreur de configuration', err instanceof Error ? err.message : 'Une erreur est survenue.');
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const data = await api<PluginListResponse>('/api/admin/plugins');
        if (data) {
          setPlugins(data.plugins || []);
          setLoadedNames(data.loaded_plugins || []);
        }
      } catch (err) {
        logger.error('Failed to fetch plugins:', err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (activeTab === 'registry') {
      const id = setTimeout(() => setLoadingRegistry(true), 0);
      (async () => {
        try {
          const data = await api<{ plugins: RegistryPlugin[] }>('/api/admin/plugins/registry');
          if (data && data.plugins) {
            setRegistryPlugins(data.plugins);
          }
        } catch (err) {
          logger.error('Failed to fetch registry:', err);
        } finally {
          clearTimeout(id);
          setLoadingRegistry(false);
        }
      })();
    }
  }, [activeTab]);

  const handleToggle = async (pluginId: string) => {
    if (!isAdmin) return;
    setToggling(pluginId);
    try {
      const res = await api<{ loaded: boolean }>(`/api/admin/plugins/${pluginId}/toggle`, {
        method: 'POST',
      });
      if (res) {
        setLoadedNames((prev) =>
          res.loaded ? [...prev, pluginId] : prev.filter((n) => n !== pluginId)
        );
        usePluginStore.getState().fetchPluginPages();
        await fetchPlugins();
        addToast('success', t('plugins.title'), res.loaded ? t('plugins.activated') : t('plugins.deactivated'));
      }
    } catch (err: unknown) {
      addToast('error', t('settings.error'), err instanceof Error ? err.message : t('plugins.toggle_error'));
    } finally {
      setToggling(null);
    }
  };

  const handleInstall = async (pluginId: string) => {
    if (!isAdmin) return;
    setInstallingPlugin(pluginId);
    const targetPlugin = registryPlugins.find(p => p.id === pluginId);
    const pluginName = targetPlugin ? targetPlugin.name : pluginId;
    try {
      const res = await api<{ status: string; message: string }>(`/api/admin/plugins/registry/${pluginId}/install`, {
        method: 'POST',
      });
      if (res && res.status === 'success') {
        addToast('success', t('plugins.title'), t('plugins.registry.install_success', { name: pluginName }));
        await fetchPlugins();
      }
    } catch (err: unknown) {
      addToast('error', t('settings.error'), err instanceof Error ? err.message : t('plugins.registry.install_failed', { name: pluginName }));
    } finally {
      setInstallingPlugin(null);
    }
  };

  const handleDelete = async (pluginId: string) => {
    if (!isAdmin) return;
    if (!confirm(`Delete plugin "${pluginId}"?`)) return;
    setDeleting(pluginId);
    try {
      const res = await api<{ status: string }>(`/api/admin/plugins/${pluginId}`, {
        method: 'DELETE',
      });
      if (res && (res.status === 'success' || res.status === 'deleted')) {
        addToast('success', t('plugins.title'), `Plugin "${pluginId}" deleted`);
        await fetchPlugins();
      }
    } catch (err: unknown) {
      addToast('error', t('settings.error'), err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeleting(null);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const token = useAuthStore.getState().accessToken;
      const res = await fetch('/api/admin/plugins/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(err.detail || 'Upload failed');
      }

      addToast('success', t('plugins.title'), t('plugins.uploaded', { name: file.name }));
      await fetchPlugins();
    } catch (err: unknown) {
      addToast('error', t('settings.error'), (err instanceof Error ? err.message : t('plugins.upload_failed')));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return {
    plugins, loadedNames, loading, toggling, uploading, deleting,
    fileInputRef, activeTab, registryPlugins, loadingRegistry,
    installingPlugin, selectedPlugin, isAdmin, t,
    setActiveTab, setSelectedPlugin, fetchPlugins, handleSaveConfig,
    handleToggle, handleInstall, handleDelete, handleUpload, closeDetailsModal,
  };
};
