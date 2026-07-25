import React from 'react';
import { Upload, RefreshCw, Grid } from 'lucide-react';
import { Spinner } from '../components/primitives/Spinner';
import { usePageTitle } from '../hooks/usePageTitle';
import { clsx } from 'clsx';
import { PluginDetailModal } from '../components/plugins/PluginDetailModal';
import { PluginInstalledView } from '../components/plugins/PluginInstalledView';
import { PluginRegistryView } from '../components/plugins/PluginRegistryView';
import { usePluginsData } from '../hooks/usePluginsData';

// Re-export types for backward compatibility with existing imports
export type { PluginInfo } from '../hooks/usePluginsData';

export const PluginsPage: React.FC = () => {
  const {
    plugins, loadedNames, loading, toggling, uploading, deleting,
    fileInputRef, activeTab, registryPlugins, loadingRegistry,
    installingPlugin, selectedPlugin, isAdmin, t,
    setActiveTab, setSelectedPlugin, fetchPlugins, handleSaveConfig,
    handleToggle, handleInstall, handleDelete, handleUpload, closeDetailsModal,
  } = usePluginsData();

  usePageTitle(t('page_title.plugins'));

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
        <PluginInstalledView
          plugins={plugins}
          loadedNames={loadedNames}
          loading={loading}
          toggling={toggling}
          deleting={deleting}
          isAdmin={isAdmin}
          onSelectPlugin={(plugin) => setSelectedPlugin(plugin)}
          onTogglePlugin={(pluginId) => handleToggle(pluginId)}
          onDeletePlugin={(pluginId) => handleDelete(pluginId)}
          t={t}
          fileInputRef={fileInputRef}
        />
      ) : (
        <PluginRegistryView
          registryPlugins={registryPlugins}
          loadingRegistry={loadingRegistry}
          plugins={plugins}
          isAdmin={isAdmin}
          installingPlugin={installingPlugin}
          onSelectPlugin={(plugin) => setSelectedPlugin(plugin)}
          onInstallPlugin={(pluginId) => handleInstall(pluginId)}
          t={t}
        />
      )}

      {selectedPlugin && (
        <PluginDetailModal
          plugin={selectedPlugin}
          onClose={closeDetailsModal}
          onSaveConfig={handleSaveConfig}
          t={t}
        />
      )}
    </div>
  );
};
