import React, { useEffect, useState } from 'react';
import { useLocale } from '../i18n';
import { usePageTitle } from '../hooks/usePageTitle';
import { usePermission } from '../hooks/usePermission';
import { api } from '../hooks/useApi';
import { Spinner } from '../components/primitives/Spinner';
import { AlertTriangle } from 'lucide-react';
import { ProfileSettingsTab } from '../components/settings/ProfileSettingsTab';
import { LLMSettingsTab } from '../components/settings/LLMSettingsTab';
import { SecuritySettingsTab } from '../components/settings/SecuritySettingsTab';
import { GeneralSettingsTab } from '../components/settings/GeneralSettingsTab';
import type { SystemSettingsResponse } from '../components/settings/types';

export const SettingsPage: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.settings'));

  const [activeTab, setActiveTab] = useState<'profile' | 'system'>('profile');
  const { can } = usePermission();

  const [systemSettings, setSystemSettings] = useState<SystemSettingsResponse | null>(null);
  const [systemLoading, setSystemLoading] = useState(false);
  const [systemError, setSystemError] = useState<string | null>(null);

  useEffect(() => {
    if (activeTab === 'system' && can('view-settings') && !systemSettings) {
      (async () => {
        setSystemLoading(true);
        setSystemError(null);
        try {
          const data = await api<SystemSettingsResponse>('/api/admin/settings');
          if (data) {
            setSystemSettings(data);
          }
        } catch (err) {
          const message = err instanceof Error ? err.message : t('settings.load_error');
          setSystemError(message);
        } finally {
          setSystemLoading(false);
        }
      })();
    }
  }, [activeTab, can, t, systemSettings]);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in font-interface">
      <div>
        <h1 className="text-xl font-extrabold tracking-wider uppercase text-text-1">
          {t('settings.system_title')}
        </h1>
        <p className="text-text-3 text-[10px] uppercase font-semibold tracking-wider mt-0.5 font-sans">
          {t('settings.system_subtitle')}
        </p>
      </div>

      <div className="border-b border-border flex gap-4 shrink-0 overflow-x-auto no-scrollbar">
        <button
          onClick={() => setActiveTab('profile')}
          className={`py-2 px-1 text-xs font-bold uppercase tracking-wider border-b-2 cursor-pointer transition-all ${
            activeTab === 'profile'
              ? 'border-accent text-accent font-extrabold'
              : 'border-transparent text-text-2 hover:text-text-1'
          }`}
        >
          {t('settings.profile_appearance')}
        </button>
        {can('view-settings') && (
          <button
            onClick={() => setActiveTab('system')}
            className={`py-2 px-1 text-xs font-bold uppercase tracking-wider border-b-2 cursor-pointer transition-all ${
              activeTab === 'system'
                ? 'border-accent text-accent font-extrabold'
                : 'border-transparent text-text-2 hover:text-text-1'
            }`}
          >
            {t('settings.master_config')}
          </button>
        )}
      </div>

      {!can('view-settings') && (
        <p className="text-[9px] text-text-3 mt-2 font-interface">
          {t('settings.master_config_locked')}
        </p>
      )}

      <div className="space-y-6">
        {activeTab === 'profile' && <ProfileSettingsTab />}

        {activeTab === 'system' && can('view-settings') && (
          <div className="space-y-6">
            {systemLoading && (
              <div className="flex flex-col items-center justify-center py-12 gap-3 text-text-3 text-xs">
                <Spinner size="sm" />
                <span>{t('settings.history_loading')}</span>
              </div>
            )}

            {systemError && (
              <div className="p-4 border border-severity-critical/20 bg-severity-critical/10 text-xs text-severity-critical rounded flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 shrink-0" />
                <span>{systemError}</span>
              </div>
            )}

            {systemSettings && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 font-sans">
                <LLMSettingsTab
                  systemSettings={systemSettings}
                  onSettingsUpdated={setSystemSettings}
                />
                <SecuritySettingsTab settings={systemSettings} />
                <GeneralSettingsTab settings={systemSettings} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
