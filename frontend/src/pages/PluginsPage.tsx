import React, { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router';
import { Package, Upload, ToggleLeft, ToggleRight, RefreshCw, Grid, FileCode, Download, Trash2, X, Play, Pause, User, Tv, Film, AlertTriangle, CheckCircle2 } from 'lucide-react';
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

  const [plexConnecting, setPlexConnecting] = useState(false);
  const [plexPinCode, setPlexPinCode] = useState('');
  const plexPollIntervalRef = useRef<number | null>(null);
  const plexPollTimeoutRef = useRef<number | null>(null);

  const clearPlexTimers = () => {
    if (plexPollIntervalRef.current) {
      window.clearInterval(plexPollIntervalRef.current);
      plexPollIntervalRef.current = null;
    }
    if (plexPollTimeoutRef.current) {
      window.clearTimeout(plexPollTimeoutRef.current);
      plexPollTimeoutRef.current = null;
    }
  };

  const [nodes, setNodes] = useState<any[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [plexDetection, setPlexDetection] = useState<any | null>(null);
  const [plexLoadingData, setPlexLoadingData] = useState(false);
  const [plexActiveTab, setPlexActiveTab] = useState<'sessions' | 'libraries' | 'users'>('sessions');
  const [plexSessions, setPlexSessions] = useState<any[]>([]);
  const [plexLibraries, setPlexLibraries] = useState<any[]>([]);
  const [plexUsers, setPlexUsers] = useState<any[]>([]);

  const fetchNodes = async () => {
    try {
      const data = await api<any[]>('/api/nodes');
      if (data) {
        setNodes(data);
        if (data.length > 0) {
          setSelectedNodeId(data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch nodes:', err);
    }
  };

  const fetchPlexData = async (nodeId: string) => {
    if (!nodeId) return;
    setPlexLoadingData(true);
    setPlexDetection(null);
    try {
      const detect = await api<any>(`/api/plugins/plex/${nodeId}/detect`);
      if (detect) {
        setPlexDetection(detect);
        if (detect.detected && detect.configured) {
          const [sessionsData, libraryData, usersData] = await Promise.all([
            api<any>(`/api/plugins/plex/${nodeId}/sessions`).catch(() => null),
            api<any>(`/api/plugins/plex/${nodeId}/library`).catch(() => null),
            api<any>(`/api/plugins/plex/${nodeId}/users`).catch(() => null),
          ]);
          setPlexSessions(sessionsData?.sessions || []);
          setPlexLibraries(libraryData?.libraries || []);
          setPlexUsers(usersData?.users || []);
        }
      }
    } catch (err) {
      console.error('Failed to fetch Plex data:', err);
    } finally {
      setPlexLoadingData(false);
    }
  };

  useEffect(() => {
    if (selectedPlugin && selectedPlugin.id === 'plex') {
      fetchNodes();
    }
  }, [selectedPlugin]);

  useEffect(() => {
    if (selectedNodeId && selectedPlugin && selectedPlugin.id === 'plex') {
      fetchPlexData(selectedNodeId);
    }
  }, [selectedNodeId, selectedPlugin]);

  useEffect(() => {
    return () => clearPlexTimers();
  }, []);

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
    clearPlexTimers();
    setPlexConnecting(false);
    setPlexPinCode('');
    setSelectedPlugin(null);
    setPlexDetection(null);
    setSelectedNodeId('');
    setPlexSessions([]);
    setPlexLibraries([]);
    setPlexUsers([]);
  };

  const handleConnectPlex = async () => {
    setPlexConnecting(true);
    clearPlexTimers();

    let clientId = localStorage.getItem('plex_client_id');
    if (!clientId) {
      clientId = 'vigile-client-' + Math.random().toString(36).substring(2, 15);
      localStorage.setItem('plex_client_id', clientId);
    }

    try {
      const res = await fetch('https://plex.tv/api/v2/pins?strong=true', {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'X-Plex-Product': 'Vigile',
          'X-Plex-Client-Identifier': clientId,
        },
      });
      if (!res.ok) throw new Error('Failed to fetch PIN');
      const data = await res.json();
      
      setPlexPinCode(data.code);

      const authUrl = `https://app.plex.tv/auth#?clientID=${clientId}&code=${data.code}&context%5Bdevice%5D%5Bproduct%5D=Vigile`;
      window.open(authUrl, 'Plex Auth', 'width=600,height=700');

      // Poll every 2 seconds
      plexPollIntervalRef.current = window.setInterval(async () => {
        try {
          const pollRes = await fetch(`https://plex.tv/api/v2/pins/${data.id}`, {
            headers: {
              'Accept': 'application/json',
              'X-Plex-Client-Identifier': clientId!,
            },
          });
          const pollData = await pollRes.json();
          if (pollData.authToken) {
            clearPlexTimers();
            // Save token to Master config endpoint
            await api('/api/admin/plugins/plex/config', {
              method: 'POST',
              body: JSON.stringify({ plex_token: pollData.authToken }),
            });
            addToast('success', 'Plex', 'Connexion réussie avec Plex !');
            setPlexConnecting(false);
            setPlexPinCode('');
            fetchPlugins();
          }
        } catch (err) {
          console.error('Plex polling error:', err);
        }
      }, 2000);

      // Set timeout of 2 mins
      plexPollTimeoutRef.current = window.setTimeout(() => {
        clearPlexTimers();
        setPlexConnecting(false);
        setPlexPinCode('');
        addToast('error', 'Plex', 'La connexion avec Plex a expiré.');
      }, 120000);

    } catch (err) {
      console.error(err);
      addToast('error', 'Plex', 'Impossible de démarrer la connexion avec Plex.');
      setPlexConnecting(false);
    }
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
                    onClick={() => setSelectedPlugin({ ...plugin, loaded: isLoaded })}
                    className={clsx(
                      'bg-surface-2 border rounded-xl p-4 transition-all duration-200 cursor-pointer hover:-translate-y-0.5 hover:shadow-md',
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
                            onClick={(e) => { e.stopPropagation(); handleToggle(plugin.id); }}
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
                            onClick={(e) => { e.stopPropagation(); handleDelete(plugin.id); }}
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
                    onClick={() => setSelectedPlugin({ ...plugin, loaded: isInstalled, hooks: [] } as any)}
                    className={clsx(
                      'bg-surface-2 border rounded-xl p-4 flex flex-col justify-between transition-all duration-200 cursor-pointer hover:-translate-y-0.5 hover:shadow-md',
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
                          onClick={(e) => { e.stopPropagation(); handleInstall(plugin.id); }}
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

      {selectedPlugin && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in" 
          onClick={closeDetailsModal}
        >
          <div
            className="w-full max-w-lg bg-surface-2 border border-border-strong/20 rounded-2xl shadow-xl overflow-hidden animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-border-strong/10 bg-surface-3/50">
              <div className="flex items-center gap-3">
                <div className={clsx(
                  'w-10 h-10 rounded-xl flex items-center justify-center',
                  selectedPlugin.loaded ? 'bg-accent/15' : 'bg-surface-3'
                )}>
                  <FileCode className={clsx(
                    'w-5 h-5',
                    selectedPlugin.loaded ? 'text-accent' : 'text-text-3'
                  )} />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-text-1">{selectedPlugin.name}</h2>
                  <div className="flex items-center gap-2 mt-0.5">
                    {selectedPlugin.version && (
                      <span className="text-[10px] font-mono font-bold text-text-3">v{selectedPlugin.version}</span>
                    )}
                    <span className={clsx(
                      'text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full',
                      selectedPlugin.loaded ? 'bg-severity-ok/10 text-severity-ok' : 'bg-surface-3 text-text-3'
                    )}>
                      {selectedPlugin.loaded ? t('plugins.loaded') : t('plugins.unloaded')}
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={closeDetailsModal}
                className="p-1.5 rounded-lg hover:bg-surface-3 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6 space-y-5 max-h-[60vh] overflow-y-auto">
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3 mb-1.5">Description</h4>
                <p className="text-xs text-text-2 leading-relaxed whitespace-pre-line">
                  {selectedPlugin.description || "Aucune description fournie pour cette extension."}
                </p>
              </div>
 
              {selectedPlugin.id === 'plex' && selectedPlugin.loaded && isAdmin && (
                <div className="p-4 bg-accent/5 border border-accent/15 rounded-xl space-y-3">
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3">Authentification Plex</h4>
                  <p className="text-[11px] text-text-2">
                    Connectez Vigile à votre Plex Media Server pour activer les diagnostics de charge automatique.
                  </p>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleConnectPlex}
                      disabled={plexConnecting}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider bg-accent hover:bg-accent-hover text-text-1 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                    >
                      {plexConnecting ? <Spinner size="sm" /> : <Package className="w-3.5 h-3.5" />}
                      Se connecter avec Plex
                    </button>
                    {plexPinCode && (
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-text-3 font-mono font-bold">Code :</span>
                        <code className="text-xs font-mono font-bold bg-surface-3 px-2 py-0.5 rounded text-accent tracking-wider animate-pulse">
                          {plexPinCode}
                        </code>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {selectedPlugin.id === 'plex' && selectedPlugin.loaded && (
                <div className="space-y-4 pt-2 border-t border-border-strong/10">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface-3/30 p-3 rounded-xl border border-border-strong/10">
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3">Serveur Cible (Node)</h4>
                      <p className="text-[10px] text-text-2 mt-0.5">Sélectionnez le nœud sur lequel inspecter Plex.</p>
                    </div>
                    <select
                      value={selectedNodeId}
                      onChange={(e) => setSelectedNodeId(e.target.value)}
                      className="px-2 py-1 text-[11px] font-semibold bg-surface border border-border-strong/20 rounded-md text-text-1 focus:outline-none focus:border-accent/40"
                    >
                      <option value="">-- Choisir un nœud --</option>
                      {nodes.map((node) => (
                        <option key={node.id} value={node.id}>
                          {node.name} ({node.hostname || 'No Host'})
                        </option>
                      ))}
                    </select>
                  </div>

                  {plexLoadingData && (
                    <div className="flex items-center justify-center p-6 gap-2">
                      <Spinner size="md" />
                      <span className="text-[11px] font-bold uppercase tracking-wider text-text-3">Analyse du nœud Plex...</span>
                    </div>
                  )}

                  {!plexLoadingData && plexDetection && (
                    <div className="space-y-4">
                      {!plexDetection.detected ? (
                        <div className="flex items-center gap-2 p-3 bg-severity-warning/10 border border-severity-warning/20 rounded-xl text-severity-warning">
                          <AlertTriangle className="w-4 h-4 shrink-0" />
                          <span className="text-xs font-semibold">Plex n'est pas détecté sur ce nœud (aucun conteneur ni service actif).</span>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between p-3 bg-severity-ok/10 border border-severity-ok/20 rounded-xl text-severity-ok">
                          <div className="flex items-center gap-2">
                            <CheckCircle2 className="w-4 h-4 shrink-0" />
                            <span className="text-xs font-semibold">
                              Plex détecté sur le port <span className="font-bold">{plexDetection.port}</span> ({plexDetection.type})
                            </span>
                          </div>
                          {plexDetection.status && (
                            <span className="text-[9px] font-bold font-mono bg-severity-ok/25 text-severity-ok px-2 py-0.5 rounded-full uppercase">
                              {plexDetection.status}
                            </span>
                          )}
                        </div>
                      )}

                      {plexDetection.detected && !plexDetection.configured && (
                        <div className="p-3 bg-severity-warning/5 border border-severity-warning/10 rounded-xl text-text-2 text-xs leading-relaxed">
                          ⚠️ Le token Plex n'est pas configuré. Veuillez utiliser le bouton de connexion ci-dessus pour lier Vigile à votre serveur Plex.
                        </div>
                      )}

                      {plexDetection.detected && plexDetection.configured && (
                        <div className="space-y-3">
                          <div className="flex border-b border-border-strong/10 gap-3">
                            {(['sessions', 'libraries', 'users'] as const).map((tab) => (
                              <button
                                key={tab}
                                onClick={() => setPlexActiveTab(tab)}
                                className={clsx(
                                  'pb-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2',
                                  plexActiveTab === tab
                                    ? 'text-accent border-accent'
                                    : 'text-text-3 border-transparent hover:text-text-2'
                                )}
                              >
                                {tab === 'sessions' && 'Sessions en cours'}
                                {tab === 'libraries' && 'Bibliothèques'}
                                {tab === 'users' && 'Utilisateurs'}
                              </button>
                            ))}
                          </div>

                          {plexActiveTab === 'sessions' && (
                            <div className="space-y-2">
                              {plexSessions.length === 0 ? (
                                <div className="text-center py-6 text-text-3 text-[11px] uppercase tracking-wider font-semibold">
                                  Aucune lecture en cours
                                </div>
                              ) : (
                                <div className="grid grid-cols-1 gap-2 max-h-[25vh] overflow-y-auto pr-1">
                                  {plexSessions.map((session, i) => (
                                    <div key={i} className="flex items-center justify-between p-3 bg-surface-3/50 border border-border-strong/15 rounded-xl">
                                      <div className="min-w-0 flex items-center gap-2">
                                        <div className="w-7 h-7 rounded-lg bg-accent/10 flex items-center justify-center text-accent shrink-0">
                                          {session.state === 'playing' ? <Play className="w-3.5 h-3.5 fill-accent" /> : <Pause className="w-3.5 h-3.5" />}
                                        </div>
                                        <div className="min-w-0">
                                          <div className="text-xs font-bold text-text-1 truncate">
                                            {session.grandparent_title ? `${session.grandparent_title} - ` : ''}{session.title}
                                          </div>
                                          <div className="flex items-center gap-2 mt-0.5 text-[10px] text-text-3">
                                            <span className="flex items-center gap-1">
                                              <User className="w-3 h-3" /> {session.user}
                                            </span>
                                            <span className="flex items-center gap-1 truncate">
                                              <Tv className="w-3 h-3" /> {session.device || 'Inconnu'}
                                            </span>
                                          </div>
                                        </div>
                                      </div>
                                      <div className="shrink-0 flex items-center gap-1.5">
                                        <span className={clsx(
                                          'text-[9px] font-bold px-1.5 py-0.5 rounded-full',
                                          session.transcode ? 'bg-severity-warning/10 text-severity-warning border border-severity-warning/15' : 'bg-severity-ok/10 text-severity-ok border border-severity-ok/15'
                                        )}>
                                          {session.transcode ? 'Transcodage' : 'Direct Play'}
                                        </span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {plexActiveTab === 'libraries' && (
                            <div className="grid grid-cols-2 gap-2 max-h-[25vh] overflow-y-auto pr-1">
                              {plexLibraries.length === 0 ? (
                                <div className="col-span-2 text-center py-6 text-text-3 text-[11px] uppercase tracking-wider font-semibold">
                                  Aucune bibliothèque trouvée
                                </div>
                              ) : (
                                plexLibraries.map((lib, i) => (
                                  <div key={i} className="p-3 bg-surface-3/50 border border-border-strong/15 rounded-xl flex items-center gap-2">
                                    <Film className="w-4 h-4 text-accent shrink-0" />
                                    <div className="min-w-0">
                                      <div className="text-xs font-bold text-text-1 truncate">{lib.title}</div>
                                      <div className="text-[9px] text-text-3 uppercase font-semibold mt-0.5">{lib.type}</div>
                                    </div>
                                  </div>
                                ))
                              )}
                            </div>
                          )}

                          {plexActiveTab === 'users' && (
                            <div className="space-y-2 max-h-[25vh] overflow-y-auto pr-1">
                              {plexUsers.length === 0 ? (
                                <div className="text-center py-6 text-text-3 text-[11px] uppercase tracking-wider font-semibold">
                                  Aucun utilisateur trouvé
                                </div>
                              ) : (
                                plexUsers.map((user, i) => (
                                  <div key={i} className="flex items-center gap-2.5 p-2.5 bg-surface-3/50 border border-border-strong/15 rounded-xl">
                                    <div className="w-6.5 h-6.5 rounded-full bg-accent-muted/20 border border-accent/25 flex items-center justify-center text-[10px] font-bold text-accent">
                                      {user.name ? user.name.substring(0, 2).toUpperCase() : 'US'}
                                    </div>
                                    <div>
                                      <div className="text-xs font-bold text-text-1">{user.name || 'Utilisateur Plex'}</div>
                                      {user.default_subtitle_language && (
                                        <div className="text-[9px] text-text-3">Langue sous-titres : {user.default_subtitle_language}</div>
                                      )}
                                    </div>
                                  </div>
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              {selectedPlugin.hooks && selectedPlugin.hooks.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3 mb-2">Points d'ancrage (Hooks)</h4>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedPlugin.hooks.map((hook) => (
                      <span
                        key={hook}
                        className="text-[9px] font-mono px-2 py-0.5 rounded-md bg-accent/5 text-accent border border-accent/10"
                      >
                        {hook}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(selectedPlugin.path || selectedPlugin.module) && (
                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-3 mb-1.5">Module / Chemin</h4>
                  <code className="text-[10px] font-mono text-text-3 bg-surface-3 px-2 py-1 rounded block truncate" title={selectedPlugin.path || selectedPlugin.module}>
                    {selectedPlugin.module || selectedPlugin.path}
                  </code>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex justify-end p-4 border-t border-border-strong/10 bg-surface-3/30">
              <button
                onClick={closeDetailsModal}
                className="px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider bg-surface border border-border-strong/20 hover:border-accent/30 text-text-2 hover:text-text-1 rounded-lg transition-colors cursor-pointer"
              >
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
