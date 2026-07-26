import React from 'react';
import { Package } from 'lucide-react';
import { EmptyState } from '../ui/EmptyState';
import { PluginCard } from './PluginCard';
import type { PluginInfo } from '../../pages/PluginsPage';

interface PluginInstalledViewProps {
  plugins: PluginInfo[];
  loadedNames: string[];
  loading: boolean;
  toggling: string | null;
  deleting: string | null;
  isAdmin: boolean;
  onSelectPlugin: (plugin: PluginInfo & { loaded: boolean }) => void;
  onTogglePlugin: (pluginId: string, e: React.MouseEvent) => void;
  onDeletePlugin: (pluginId: string, e: React.MouseEvent) => void;
  t: (key: string, params?: Record<string, string>) => string;
  fileInputRef: React.RefObject<HTMLInputElement>;
}

export const PluginInstalledView: React.FC<PluginInstalledViewProps> = ({
  plugins, loadedNames, loading, toggling, deleting,
  isAdmin, onSelectPlugin, onTogglePlugin, onDeletePlugin, t, fileInputRef,
}) => {
  if (loading && plugins.length === 0) {
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

  if (!loading && plugins.length === 0) {
    return (
      <EmptyState
        icon={<Package className="w-12 h-12" />}
        title={t("plugins.empty_title")}
        description={t("plugins.empty_description")}
        action={isAdmin ? {
          label: t('plugins.upload_action'),
          onClick: () => fileInputRef.current?.click(),
        } : undefined}
      />
    );
  }

  if (plugins.length > 0) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {plugins.map((plugin) => {
          const isLoaded = loadedNames.includes(plugin.id);
          return (
            <PluginCard
              key={plugin.name}
              plugin={plugin}
              isLoaded={isLoaded}
              isAdmin={isAdmin}
              toggling={toggling === plugin.id}
              deleting={deleting === plugin.id}
              onSelect={() => onSelectPlugin({ ...plugin, loaded: isLoaded })}
              onToggle={(e) => { e.stopPropagation(); onTogglePlugin(plugin.id, e); }}
              onDelete={(e) => { e.stopPropagation(); onDeletePlugin(plugin.id, e); }}
              t={t}
            />
          );
        })}
      </div>
    );
  }

  return null;
};
