import React, { useEffect, useState, useRef } from 'react';
import { Package, Upload, ToggleLeft, ToggleRight, RefreshCw, Grid, FileCode, Download, Trash2 } from 'lucide-react';
import { api } from '../hooks/useApi';
import { useAuthStore } from '../store/authStore';
import { usePermission } from '../hooks/usePermission';
import { useToastStore } from '../store/useToastStore';
import { EmptyState } from '../components/ui/EmptyState';
import { Spinner } from '../components/primitives/Spinner';
import { useLocale } from '../i18n';
import { usePageTitle } from '../hooks/usePageTitle';
import { clsx } from 'clsx';

interface PluginInfo {
  id: string;
  name: string;
  path: string;
  module: string;
  loaded: boolean;
  hooks: string[];
  error?: string;
  version?: string;
  description?: string;
}

interface PluginListResponse {
  loaded_plugins: string[];
  plugins: PluginInfo[];
}

interface RegistryPlugin {
  id: string;
  name: string;
  description: string;
  author: string;
  version: string;
  download_url: string;
}

export const PluginsPage: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.plugins'));
  const { isAdmin } = usePermission();
  const addToast = useToastStore((s) => s.addToast);

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

  const fetchPlugins = async () => {
    setLoading(true);
    try {
      const data = await api<PluginListResponse>('/api/admin/plugins');
      if (data) {
        setPlugins(data.plugins || []);
        setLoadedNames(data.loaded_plugins || []);
      }
    } catch (err) {
      console.error('Failed to fetch plugins:', err);
    } finally {
      setLoading(false);
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
        console.error('Failed to fetch plugins:', err);
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
          console.error('Failed to fetch registry:', err);
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
      if (res && res.status === 'deleted') {
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

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold uppercase tracking-wider text-text-1 flex items-center gap-2">
            <Grid className="w-5 h-5 text-accent" />
            {t('nav.plugins')}
          </h1>
          <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
            {t('plugins.count', { total: plugins.length, loaded: loadedNames.length })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchPlugins}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider bg-surface border border-border-strong/20 rounded-lg text-text-2 hover:text-text-1 hover:border-accent/30 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={clsx('w-3 h-3', loading && 'animate-spin')} />
            {t('plugins.refresh')}
          </button>
          {isAdmin && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept=".py"
                onChange={handleUpload}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider bg-accent hover:bg-accent-hover text-text-1 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
              >
                {uploading ? <Spinner size="sm" /> : <Upload className="w-3 h-3" />}
                {t("plugins.upload")}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border-strong/10 gap-4">
        <button
          onClick={() => setActiveTab('installed')}
          className={clsx(
            'pb-2 text-[11px] font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2',
            activeTab === 'installed'
              ? 'text-accent border-accent'
              : 'text-text-3 border-transparent hover:text-text-2'
          )}
        >
          {t('plugins.tabs.installed')}
        </button>
        <button
          onClick={() => setActiveTab('registry')}
          className={clsx(
            'pb-2 text-[11px] font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2',
            activeTab === 'registry'
              ? 'text-accent border-accent'
              : 'text-text-3 border-transparent hover:text-text-2'
          )}
        >
          {t('plugins.tabs.registry')}
        </button>
      </div>

      {activeTab === 'installed' ? (
        <>
          {loading && plugins.length === 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-surface-2 border border-border-strong/20 rounded-xl p-4 animate-pulse space-y-3">
                  <div className="h-4 bg-surface-3 rounded w-1/2" />
                  <div className="h-3 bg-surface-3 rounded w-3/4" />
                  <div className="h-3 bg-surface-3 rounded w-1/3" />
                </div>
              ))}
            </div>
          )}

          {!loading && plugins.length === 0 && (
            <EmptyState
              icon={<Package className="w-12 h-12" />}
              title={t("plugins.empty_title")}
              description={t("plugins.empty_description")}
              action={isAdmin ? {
                label: t('plugins.upload_action'),
                onClick: () => fileInputRef.current?.click(),
              } : undefined}
            />
          )}

          {plugins.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {plugins.map((plugin) => {
                const isLoaded = loadedNames.includes(plugin.id);
                return (
                  <div
                    key={plugin.name}
                    className={clsx(
                      'bg-surface-2 border rounded-xl p-4 transition-all duration-200',
                      isLoaded
                        ? 'border-accent/20 hover:border-accent/30'
                        : 'border-border-strong/20 hover:border-border-strong/40'
                    )}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className={clsx(
                          'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                          isLoaded ? 'bg-accent/10' : 'bg-surface-3'
                        )}>
                          <FileCode className={clsx(
                            'w-4 h-4',
                            isLoaded ? 'text-accent' : 'text-text-3'
                          )} />
                        </div>
                        <div className="min-w-0">
                          <h3 className="text-sm font-bold text-text-1 truncate">{plugin.name}</h3>
                          <span className={clsx(
                            'text-[9px] font-mono font-bold uppercase',
                            isLoaded ? 'text-severity-ok' : 'text-text-3'
                          )}>
                            {isLoaded ? t('plugins.loaded') : t('plugins.unloaded')}
                          </span>
                        </div>
                      </div>
                      {isAdmin && (
                        <>
                          <button
                            onClick={() => handleToggle(plugin.id)}
                            disabled={toggling === plugin.id}
                            className="shrink-0 p-1 rounded hover:bg-surface-3 transition-colors cursor-pointer disabled:opacity-50"
                            title={isLoaded ? t('plugins.deactivate') : t('plugins.activate')}
                          >
                            {toggling === plugin.id ? (
                              <Spinner size="sm" />
                            ) : isLoaded ? (
                              <ToggleRight className="w-4 h-4 text-accent" />
                            ) : (
                              <ToggleLeft className="w-4 h-4 text-text-3" />
                            )}
                          </button>
                          <button
                            onClick={() => handleDelete(plugin.id)}
                            disabled={deleting === plugin.id}
                            className="shrink-0 p-1 rounded hover:bg-severity-critical/15 transition-colors cursor-pointer disabled:opacity-50 text-text-3 hover:text-severity-critical"
                            title="Uninstall"
                          >
                            {deleting === plugin.id ? (
                              <Spinner size="sm" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        </>
                      )}
                    </div>

                    {plugin.description && (
                      <p className="text-[10px] text-text-2 mb-2 line-clamp-2 leading-relaxed">
                        {plugin.description}
                      </p>
                    )}

                    <div className="mb-2">
                      <code className="text-[9px] font-mono text-text-3 bg-surface-3 px-1.5 py-0.5 rounded truncate block">
                        {plugin.module || plugin.path}
                      </code>
                    </div>

                    {plugin.hooks && plugin.hooks.length > 0 && (
                      <div className="space-y-1">
                        <span className="text-[9px] font-bold uppercase tracking-wider text-text-3">{t('plugins.hooks_label')}</span>
                        <div className="flex flex-wrap gap-1">
                          {plugin.hooks.map((hook) => (
                            <span
                              key={hook}
                              className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-accent/5 text-accent border border-accent/10"
                            >
                              {hook}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {plugin.error && (
                      <div className="mt-2 p-2 bg-severity-critical/10 border border-severity-critical/20 rounded-lg">
                        <p className="text-[10px] text-severity-critical font-mono">{plugin.error}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      ) : (
        <>
          {loadingRegistry && registryPlugins.length === 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-surface-2 border border-border-strong/20 rounded-xl p-4 animate-pulse space-y-3">
                  <div className="h-4 bg-surface-3 rounded w-1/2" />
                  <div className="h-3 bg-surface-3 rounded w-3/4" />
                  <div className="h-3 bg-surface-3 rounded w-1/3" />
                </div>
              ))}
            </div>
          )}

          {!loadingRegistry && registryPlugins.length === 0 && (
            <EmptyState
              icon={<Package className="w-12 h-12" />}
              title={t("plugins.registry.empty")}
              description={t("plugins.registry.empty")}
            />
          )}

          {registryPlugins.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {registryPlugins.map((plugin) => {
                const isInstalled = plugins.some(p => p.id === plugin.id);
                const isInstalling = installingPlugin === plugin.id;

                return (
                  <div
                    key={plugin.id}
                    className={clsx(
                      'bg-surface-2 border rounded-xl p-4 flex flex-col justify-between transition-all duration-200',
                      isInstalled
                        ? 'border-border-strong/10 opacity-70'
                        : 'border-border-strong/20 hover:border-border-strong/40'
                    )}
                  >
                    <div>
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-2 min-w-0">
                          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-surface-3 shrink-0">
                            <FileCode className="w-4 h-4 text-text-3" />
                          </div>
                          <div className="min-w-0">
                            <h3 className="text-sm font-bold text-text-1 truncate">{plugin.name}</h3>
                            <span className="text-[9px] font-mono font-bold text-text-3 uppercase">
                              {t('plugins.registry.version')}: {plugin.version}
                            </span>
                          </div>
                        </div>
                      </div>

                      <p className="text-xs text-text-2 mb-4 line-clamp-3">
                        {plugin.description}
                      </p>

                      <div className="space-y-1 text-[10px] text-text-3 font-medium mb-4">
                        <div>
                          <span className="font-bold uppercase tracking-wider text-[9px] block text-text-3 mb-0.5">
                            {t('plugins.registry.author')}
                          </span>
                          <span className="text-text-2">{plugin.author}</span>
                        </div>
                      </div>
                    </div>

                    <div>
                      {isInstalled ? (
                        <button
                          disabled
                          className="w-full py-1.5 px-3 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-surface border border-border-strong/20 text-text-3 cursor-not-allowed text-center"
                        >
                          {t('plugins.registry.installed')}
                        </button>
                      ) : (
                        <button
                          onClick={() => handleInstall(plugin.id)}
                          disabled={!isAdmin || isInstalling}
                          className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-accent hover:bg-accent-hover text-text-1 transition-colors disabled:opacity-50 cursor-pointer"
                        >
                          {isInstalling ? (
                            <>
                              <Spinner size="sm" />
                              {t('plugins.registry.installing')}
                            </>
                          ) : (
                            <>
                              <Download className="w-3 h-3" />
                              {t('plugins.registry.install')}
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};
