import React from 'react';
import { Puzzle } from 'lucide-react';
import { useLocale } from '../../i18n';
import type { SystemSettingsResponse } from './types';

interface PluginsSettingsTabProps {
  settings: SystemSettingsResponse;
}

export const PluginsSettingsTab: React.FC<PluginsSettingsTabProps> = ({ settings }) => {
  const { t } = useLocale();

  return (
    <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4">
      <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2 font-interface">
        <Puzzle className="w-4 h-4 text-accent" />
        <span>{t('settings.plugins_title')}</span>
      </h3>
      <div className="space-y-3 text-xs">
        <div className="flex justify-between items-center py-1">
          <span className="text-text-3">{t('settings.plugins_dir')}</span>
          <span className="font-mono text-text-1 font-semibold break-all text-right ml-2">
            {settings.plugins_dir || '—'}
          </span>
        </div>
      </div>
    </div>
  );
};
