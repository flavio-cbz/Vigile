import React from 'react';
import { Package } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import { RegistryPluginCard } from './RegistryPluginCard';
import type { PluginInfo, RegistryPlugin } from '../../hooks/usePluginsData';

interface PluginRegistryViewProps {
  registryPlugins: RegistryPlugin[];
  loadingRegistry: boolean;
  plugins: PluginInfo[];
  isAdmin: boolean;
  installingPlugin: string | null;
  onSelectPlugin: (plugin: PluginInfo) => void;
  onInstallPlugin: (pluginId: string, e: React.MouseEvent) => void;
  t: (key: string, params?: Record<string, string>) => string;
}

export const PluginRegistryView: React.FC<PluginRegistryViewProps> = ({
  registryPlugins, loadingRegistry, plugins, isAdmin,
  installingPlugin, onSelectPlugin, onInstallPlugin, t,
}) => {
  if (loadingRegistry && registryPlugins.length === 0) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="bg-surface-2 border border-border-strong/20 rounded-xl p-4 animate-pulse space-y-3">
            <div className="h-4 bg-surface-3 rounded w-1/2" />
            <div className="h-3 bg-surface-3 rounded w-3/4" />
            <div className="h-3 bg-surface-3 rounded w-1/3" />
          </div>
        ))}
      </div>
    );
  }

  if (!loadingRegistry && registryPlugins.length === 0) {
    return (
      <EmptyState
        icon={<Package className="w-12 h-12" />}
        title={t("plugins.registry.empty")}
        description={t("plugins.registry.empty")}
      />
    );
  }

  if (registryPlugins.length > 0) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {registryPlugins.map((plugin) => {
          const isInstalled = plugins.some(p => p.id === plugin.id);
          return (
            <RegistryPluginCard
              key={plugin.id}
              plugin={plugin}
              isInstalled={isInstalled}
              isAdmin={isAdmin}
              isInstalling={installingPlugin === plugin.id}
              onSelect={() => onSelectPlugin({ ...plugin, loaded: isInstalled, hooks: [] } as PluginInfo)}
              onInstall={(e) => { e.stopPropagation(); onInstallPlugin(plugin.id, e); }}
              t={t}
            />
          );
        })}
      </div>
    );
  }

  return null;
};
