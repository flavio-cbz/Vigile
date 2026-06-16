import React, { useEffect, useState, useRef } from 'react';
import { Package, Upload, ToggleLeft, ToggleRight, RefreshCw, Grid, FileCode } from 'lucide-react';
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

export const PluginsPage: React.FC = () => {
  usePageTitle('Plugins');
  const { isAdmin } = usePermission();
  const { t } = useLocale();
  const addToast = useToastStore((s) => s.addToast);

  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loadedNames, setLoadedNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    fetchPlugins();
  }, []);

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
        addToast('success', 'Plugin', res.loaded ? 'Plugin activé.' : 'Plugin désactivé.');
      }
    } catch (err: Error) {
      addToast('error', 'Erreur', err.message || 'Impossible de basculer le plugin.');
    } finally {
      setToggling(null);
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

      addToast('success', 'Plugin', `Plugin "${file.name}" uploadé avec succès.`);
      await fetchPlugins();
    } catch (err: Error) {
      addToast('error', 'Erreur', err.message || 'Échec de l\'upload du plugin.');
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
            {plugins.length} plugin{plugins.length !== 1 ? 's' : ''} · {loadedNames.length} chargé{loadedNames.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchPlugins}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider bg-surface border border-border-strong/20 rounded-lg text-text-2 hover:text-text-1 hover:border-accent/30 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={clsx('w-3 h-3', loading && 'animate-spin')} />
            Actualiser
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
                Upload
              </button>
            </>
          )}
        </div>
      </div>

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
          title="Aucun plugin"
          description="Le répertoire des plugins est vide. Téléchargez un plugin Python pour commencer."
          action={isAdmin ? {
            label: 'Uploader un plugin',
            onClick: () => fileInputRef.current?.click(),
          } : undefined}
        />
      )}

      {plugins.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {plugins.map((plugin) => {
            const isLoaded = loadedNames.includes(plugin.name);
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
                        {isLoaded ? 'Chargé' : 'Déchargé'}
                      </span>
                    </div>
                  </div>
                  {isAdmin && (
                    <button
                      onClick={() => handleToggle(plugin.name)}
                      disabled={toggling === plugin.name}
                      className="shrink-0 p-1 rounded hover:bg-surface-3 transition-colors cursor-pointer disabled:opacity-50"
                      title={isLoaded ? 'Désactiver' : 'Activer'}
                    >
                      {toggling === plugin.name ? (
                        <Spinner size="sm" />
                      ) : isLoaded ? (
                        <ToggleRight className="w-4 h-4 text-accent" />
                      ) : (
                        <ToggleLeft className="w-4 h-4 text-text-3" />
                      )}
                    </button>
                  )}
                </div>

                <div className="mb-2">
                  <code className="text-[9px] font-mono text-text-3 bg-surface-3 px-1.5 py-0.5 rounded truncate block">
                    {plugin.module || plugin.path}
                  </code>
                </div>

                {plugin.hooks && plugin.hooks.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-text-3">Hooks</span>
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
    </div>
  );
};
