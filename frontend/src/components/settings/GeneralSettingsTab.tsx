import React from 'react';
import { Database } from 'lucide-react';
import { useLocale } from '../../i18n';
import type { SystemSettingsResponse } from './types';

interface GeneralSettingsTabProps {
  settings: SystemSettingsResponse;
}

export const GeneralSettingsTab: React.FC<GeneralSettingsTabProps> = ({ settings }) => {
  const { t } = useLocale();

  return (
    <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4 md:col-span-2">
      <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2 font-interface">
        <Database className="w-4 h-4 text-accent" />
        <span>{t('settings.master_specs')}</span>
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-xs">
        <div className="flex justify-between items-center py-1 border-b border-border/40">
          <span className="text-text-3">{t('settings.listen_host')}</span>
          <span className="font-mono text-text-1 font-semibold">{settings.host}</span>
        </div>
        <div className="flex justify-between items-center py-1 border-b border-border/40">
          <span className="text-text-3">{t('settings.listen_port')}</span>
          <span className="font-mono text-text-1 font-semibold">{settings.port}</span>
        </div>
        <div className="flex justify-between items-center py-1 border-b border-border/40">
          <span className="text-text-3">{t('settings.debug_mode')}</span>
          <span className={`font-semibold ${settings.debug ? 'text-severity-warning' : 'text-severity-ok'}`}>
            {settings.debug ? t('settings.debug_active') : t('settings.inactive')}
          </span>
        </div>
        <div className="flex justify-between items-center py-1 border-b border-border/40">
          <span className="text-text-3">{t('settings.heartbeat_uptime')}</span>
          <span className="font-mono text-text-1 font-semibold">{settings.heartbeat_interval}s</span>
        </div>
        <div className="flex justify-between items-start py-1 border-b border-border/40 sm:col-span-2">
          <span className="text-text-3 shrink-0 mr-4">{t('settings.sqlite_db')}</span>
          <span className="font-mono text-text-2 break-all text-right font-medium select-all" title={settings.database_path}>
            {settings.database_path || '—'}
          </span>
        </div>
        <div className="flex justify-between items-start py-1 sm:col-span-2">
          <span className="text-text-3 shrink-0 mr-4">{t('settings.external_url')}</span>
          <span className="font-mono text-text-2 break-all text-right font-medium select-all" title={settings.master_url}>
            {settings.master_url || '—'}
          </span>
        </div>
      </div>
    </div>
  );
};
