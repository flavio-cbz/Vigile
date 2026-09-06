import React from 'react';
import { Upload, RefreshCw, Grid } from 'lucide-react';
import { PageHeader } from '../components/blocks/PageHeader';
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
    disabling, enabling,
    fileInputRef, activeTab, registryPlugins, loadingRegistry,
    installingPlugin, selectedPlugin, isAdmin, t,
    setActiveTab, setSelectedPlugin, fetchPlugins, handleSaveConfig,
    handleToggle, handleInstall, handleDelete, handleUpload, closeDetailsModal,
    handleDisable, handleEnable,
  } = usePluginsData();

  usePageTitle(t('page_title.plugins'));

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in">
      <PageHeader
        title={t('nav.plugins')}
        icon={<Grid className="w-5 h-5" />}
        subtitle={t('plugins.count', { total: plugins.length, loaded: loadedNames.length })}
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={fetchPlugins}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw className={clsx('w-3.5 h-3.5', loading && 'animate-spin')} />
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
                  className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg border border-border-strong/50 bg-accent hover:bg-accent-hover text-bg font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 disabled:opacity-50 cursor-pointer"
                >
                  {uploading ? <Spinner size="sm" /> : <Upload className="w-3.5 h-3.5" />}
                  {t("plugins.upload")}
                </button>
              </>
            )}
          </div>
        }
      />

      <div className="flex border-b border-border-strong/10 gap-4">
        <button
          onClick={() => setActiveTab('installed')}
          className={clsx(
            'pb-2 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2',
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
            'pb-2 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2',
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
          isAdmin={isAdmin}
          disabling={disabling}
          enabling={enabling}
          onDisable={handleDisable}
          onEnable={handleEnable}
          onFetchPlugins={fetchPlugins}
          t={t}
        />
      )}
    </div>
  );
};
