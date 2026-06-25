import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { usePermission } from '../hooks/usePermission';
import { useUiStore, type ThemeKey } from '../store/uiStore';
import { api } from '../hooks/useApi';
import { Spinner } from '../components/primitives/Spinner';
import {
  User,
  Key,
  Cpu,
  Lock,
  RefreshCw,
  Database,
  ShieldCheck,
  AlertTriangle,
  Eye,
  EyeOff,
  Palette,
} from 'lucide-react';
import { themes } from '../design/themes';
import { useLocale } from '../i18n';
import { usePageTitle } from '../hooks/usePageTitle';

interface SystemSettingsResponse {
  master_url: string;
  host: string;
  port: number;
  debug: boolean;
  database_path: string;
  server_secret_key: string;
  jwt_secret_key: string;
  jwt_algorithm: string;
  jwt_access_token_ttl: number;
  jwt_refresh_token_ttl: number;
  join_token_ttl: number;
  worker_token_ttl: number;
  worker_token_rotation: number;
  heartbeat_interval: number;
  heartbeat_lost_threshold: number;
  heartbeat_stale_threshold: number;
  master_key_path: string;
  cors_origins: string[];
  trusted_proxies: string[];
  enforce_https: boolean;
  llm_base_url: string;
  llm_api_key: string;
  llm_model: string;
  plugins_dir: string;
}

export const SettingsPage: React.FC = () => {
  const { t, locale, setLocale } = useLocale();
  usePageTitle(t('page_title.settings'));
  const { user, logout } = useAuthStore();
  const { theme, setTheme } = useUiStore();
  const availableThemes = Object.keys(themes) as ThemeKey[];

  const [activeTab, setActiveTab] = useState<'profile' | 'system'>('profile');
  const { isAdmin, can } = usePermission();

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordFeedback, setPasswordFeedback] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  const [systemSettings, setSystemSettings] = useState<SystemSettingsResponse | null>(null);
  const [systemLoading, setSystemLoading] = useState(false);
  const [systemError, setSystemError] = useState<string | null>(null);

  const [llmModel, setLlmModel] = useState('');
  const [llmBaseUrl, setLlmBaseUrl] = useState('');
  const [llmApiKey, setLlmApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmTesting, setLlmTesting] = useState(false);
  const [llmFeedback, setLlmFeedback] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  useEffect(() => {
    if (systemSettings) {
      setLlmModel(systemSettings.llm_model || '');
      setLlmBaseUrl(systemSettings.llm_base_url || '');
      setLlmApiKey(systemSettings.llm_api_key || '');
    }
  }, [systemSettings]);

  const handleTestLlmConnection = async () => {
    if (user?.username === 'guest') return;
    setLlmTesting(true);
    setLlmFeedback(null);
    try {
      const data = await api<{ message: string }>('/api/admin/settings/llm/test', {
        method: 'POST',
        body: JSON.stringify({
          llm_base_url: llmBaseUrl,
          llm_api_key: llmApiKey,
          llm_model: llmModel
        })
      });
      if (data) {
        setLlmFeedback({ type: 'success', msg: data.message || t('settings.llm_valid') });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('settings.llm_test_error');
      setLlmFeedback({ type: 'error', msg: message });
    } finally {
      setLlmTesting(false);
    }
  };

  const handleSaveLlmSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (user?.username === 'guest') return;
    setLlmSaving(true);
    setLlmFeedback(null);
    try {
      const data = await api<SystemSettingsResponse>('/api/admin/settings/llm', {
        method: 'POST',
        body: JSON.stringify({
          llm_base_url: llmBaseUrl,
          llm_api_key: llmApiKey,
          llm_model: llmModel
        })
      });
      if (data) {
        setSystemSettings(data);
        setLlmFeedback({ type: 'success', msg: t('settings.llm_saved') });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('settings.llm_save_error');
      setLlmFeedback({ type: 'error', msg: message });
    } finally {
      setLlmSaving(false);
    }
  };

  const fetchSystemSettings = async () => {
    if (!can('view-settings')) return;
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
  };

  useEffect(() => {
    if (activeTab === 'system' && can('view-settings') && !systemSettings) {
      fetchSystemSettings();
    }
  }, [activeTab, can]);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordFeedback(null);

    if (newPassword.length < 8) {
      setPasswordFeedback({ type: 'error', msg: t('settings.password_minlength') });
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordFeedback({ type: 'error', msg: t('settings.password_mismatch') });
      return;
    }

    setPasswordLoading(true);
    try {
      await api<unknown>('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword
        })
      });

      setPasswordFeedback({ type: 'success', msg: t('settings.password_updated') });
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setTimeout(() => {
        logout();
      }, 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : t('settings.password_invalid');
      setPasswordFeedback({ type: 'error', msg: message });
    } finally {
      setPasswordLoading(false);
    }
  };

  const formatDuration = (seconds: number) => {
    if (seconds >= 86400) {
      const days = Math.round(seconds / 86400);
      return `${days} jour${days > 1 ? 's' : ''}`;
    }
    if (seconds >= 3600) {
      const hours = Math.round(seconds / 3600);
      return `${hours} heure${hours > 1 ? 's' : ''}`;
    }
    if (seconds >= 60) {
      const mins = Math.round(seconds / 60);
      return `${mins} minute${mins > 1 ? 's' : ''}`;
    }
    return `${seconds} secondes`;
  };

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
        {activeTab === 'profile' && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-stretch">
            <div className="md:col-span-5 space-y-6">
              <div className="p-5 border border-border rounded-xl bg-surface shadow">
                <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <User className="w-4 h-4 text-accent" />
                  <span>{t('settings.your_profile')}</span>
                </h3>

                <div className="flex items-center gap-3 p-3 bg-surface-2 border border-border rounded">
                  <div className="w-10 h-10 rounded-full border border-accent bg-accent-muted flex items-center justify-center font-bold text-accent">
                    {user?.username?.substring(0, 2).toUpperCase() || 'US'}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-text-1 truncate">{user?.username}</p>
                    <p className="text-[9px] font-mono text-accent uppercase tracking-wider mt-0.5">{t('sidebar.role_label', { role: user?.role || '' })}</p>
                  </div>
                </div>

                <div className="mt-4 space-y-2.5 text-xs font-sans">
                  <div className="flex justify-between items-center py-1.5 border-b border-border/40">
                    <span className="text-text-3 font-medium">{t('settings.user_id')}</span>
                    <span className="font-mono text-text-2 select-all break-all text-right ml-2 text-[10.5px]" title={user?.user_id}>
                      {user?.user_id?.substring(0, 8)}…
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-1.5">
                    <span className="text-text-3 font-medium">{t('settings.demo_mode')}</span>
                    <span className="font-bold text-text-2">
                      {user?.username === 'guest' ? t('settings.enabled') : t('settings.disabled')}
                    </span>
                  </div>
                </div>
              </div>

              <div className="p-5 border border-border rounded-xl bg-surface shadow">
                <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <Palette className="w-4 h-4 text-accent" />
                  <span>{t('settings.visual_customization')}</span>
                </h3>

                <div className="space-y-3 font-sans">
                  <label className="block text-[10px] font-bold text-text-3 uppercase tracking-wider">
                    {t('settings.active_theme')}
                  </label>
                  <div className="grid grid-cols-2 gap-2 font-interface">
                    {availableThemes.map((t) => (
                      <button
                        key={t}
                        onClick={() => setTheme(t)}
                        className={`p-3 rounded-lg border text-left flex flex-col justify-between h-18 cursor-pointer select-none transition-all ${
                          theme === t
                            ? 'border-accent bg-accent-muted'
                            : 'border-border bg-surface hover:bg-surface-2'
                        }`}
                      >
                        <span className="text-[9px] font-extrabold uppercase tracking-wide text-text-1">
                          {t.replace('-', ' ')}
                        </span>
                        <div className="flex gap-1.5 mt-2">
                          <span
                            className="w-3.5 h-3.5 rounded-full border border-border"
                            style={{ backgroundColor: themes[t]['--bg'] }}
                          />
                          <span
                            className="w-3.5 h-3.5 rounded-full border border-border"
                            style={{ backgroundColor: themes[t]['--surface'] }}
                          />
                          <span
                            className="w-3.5 h-3.5 rounded-full border border-border"
                            style={{ backgroundColor: themes[t]['--accent'] }}
                          />
                        </div>
                      </button>
                    ))}
                  </div>

                  <div className="border-t border-border/40 my-4" />

                  <label className="block text-[10px] font-bold text-text-3 uppercase tracking-wider mb-1.5 font-interface">
                    {t('settings.language')}
                  </label>
                  <div className="flex gap-2 font-interface">
                    <button
                      onClick={() => setLocale('fr')}
                      className={`flex-1 p-2 rounded-lg border text-center text-xs font-bold cursor-pointer transition-all ${
                        locale === 'fr'
                          ? 'border-accent bg-accent-muted text-text-1'
                          : 'border-border bg-surface text-text-3 hover:text-text-2 hover:bg-surface-2'
                      }`}
                    >
                      {t('settings.lang_fr_full')}
                    </button>
                    <button
                      onClick={() => setLocale('en')}
                      className={`flex-1 p-2 rounded-lg border text-center text-xs font-bold cursor-pointer transition-all ${
                        locale === 'en'
                          ? 'border-accent bg-accent-muted text-text-1'
                          : 'border-border bg-surface text-text-3 hover:text-text-2 hover:bg-surface-2'
                      }`}
                    >
                      {t('settings.lang_en_full')}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="md:col-span-7">
              <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4">
                <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2">
                  <Key className="w-4 h-4 text-accent" />
                  <span>{t('settings.change_password')}</span>
                </h3>

                {passwordFeedback && (
                  <div className={`p-3.5 rounded-lg border text-xs leading-relaxed font-sans font-semibold ${
                    passwordFeedback.type === 'success'
                      ? 'bg-severity-ok/10 border-severity-ok/20 text-severity-ok'
                      : 'bg-severity-critical/10 border-severity-critical/20 text-severity-critical'
                  }`}>
                    {passwordFeedback.msg}
                  </div>
                )}

                {user?.username === 'guest' ? (
                  <div className="p-4 border border-dashed border-border bg-surface-2 rounded text-xs text-text-3 font-sans leading-relaxed">
                    {t('settings.password_locked')}
                  </div>
                ) : (
                  <form onSubmit={handlePasswordChange} className="space-y-4 font-sans text-xs">
                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
                        {t('settings.current_password')}
                      </label>
                      <input
                        type="password"
                        required
                        disabled={passwordLoading}
                        value={oldPassword}
                        onChange={(e) => setOldPassword(e.target.value)}
                        placeholder={`${t('settings.current_password')}...`}
                        className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
                          {t('settings.new_password')}
                        </label>
                        <input
                          type="password"
                          required
                          disabled={passwordLoading}
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder={t('settings.new_password_placeholder')}
                          className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
                          {t('settings.confirm')}
                        </label>
                        <input
                          type="password"
                          required
                          disabled={passwordLoading}
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          placeholder={t('settings.confirm_password_placeholder')}
                          className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={passwordLoading || !oldPassword.trim() || !newPassword.trim() || !confirmPassword.trim()}
                      className="bg-accent hover:bg-accent-hover text-text-1 py-2 px-5 font-interface font-bold tracking-wider uppercase rounded shadow cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 transition-all mt-4"
                    >
                      {passwordLoading ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Lock className="w-3.5 h-3.5" />
                      )}
                      <span>{t('settings.save_password')}</span>
                    </button>
                  </form>
                )}
              </div>
            </div>
          </div>
        )}

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
                <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4">
                  <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2 font-interface">
                    <Cpu className="w-4 h-4 text-accent" />
                    <span>{t('settings.copilot_config')}</span>
                  </h3>

                  {llmFeedback && (
                    <div className={`p-3.5 rounded border text-xs leading-relaxed font-semibold ${
                      llmFeedback.type === 'success'
                        ? 'bg-severity-ok/10 border-severity-ok/20 text-severity-ok'
                        : 'bg-severity-critical/10 border-severity-critical/20 text-severity-critical'
                    }`}>
                      {llmFeedback.msg}
                    </div>
                  )}

                  {user?.username === 'guest' ? (
                    <div className="p-3.5 rounded border border-warning/20 bg-warning-subtle text-xs text-warning leading-relaxed flex items-start gap-2.5">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>
                        {t('settings.llm_locked')}
                      </span>
                    </div>
                  ) : null}

                  <form onSubmit={handleSaveLlmSettings} className="space-y-4 text-xs">
                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
                        {t('settings.llm_model')}
                      </label>
                      <input
                        type="text"
                        required
                        disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
                        value={llmModel}
                        onChange={(e) => setLlmModel(e.target.value)}
                        placeholder={t('settings.llm_model_placeholder')}
                        className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 font-mono focus:outline-none placeholder:text-text-3"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
                        {t('settings.llm_endpoint')}
                      </label>
                      <input
                        type="text"
                        required
                        disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
                        value={llmBaseUrl}
                        onChange={(e) => setLlmBaseUrl(e.target.value)}
                        placeholder={t('settings.llm_endpoint_placeholder')}
                        className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 font-mono focus:outline-none placeholder:text-text-3"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-extrabold text-text-3 uppercase tracking-wider font-interface">
                        {t('settings.llm_api_key')}
                      </label>
                      <div className="relative">
                        <input
                          type={showApiKey ? "text" : "password"}
                          required
                          disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
                          value={llmApiKey}
                          onChange={(e) => setLlmApiKey(e.target.value)}
                          placeholder={t('settings.llm_api_key_placeholder')}
                          className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 pr-10 text-text-1 font-mono focus:outline-none placeholder:text-text-3"
                        />
                        <button
                          type="button"
                          onClick={() => setShowApiKey(!showApiKey)}
                          disabled={user?.username === 'guest' || !isAdmin}
                          className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-3 hover:text-text-1 cursor-pointer border-0 bg-transparent"
                        >
                          {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-3 pt-2 font-interface">
                      <button
                        type="button"
                        onClick={handleTestLlmConnection}
                        disabled={llmSaving || llmTesting || !llmBaseUrl || user?.username === 'guest' || !isAdmin}
                        className="btn border border-border hover:border-border-strong py-2 flex-1 flex items-center justify-center gap-1.5 text-text-2 hover:text-text-1 rounded cursor-pointer disabled:opacity-50"
                      >
                        {llmTesting ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <RefreshCw className="w-3.5 h-3.5" />
                        )}
                        <span>{t('settings.llm_test')}</span>
                      </button>

                      <button
                        type="submit"
                        disabled={llmSaving || llmTesting || user?.username === 'guest' || !isAdmin}
                        className="btn bg-accent hover:bg-accent-hover text-text-1 py-2 flex-1 flex items-center justify-center gap-1.5 rounded cursor-pointer shadow disabled:opacity-50"
                      >
                        {llmSaving ? (
                          <Spinner size="sm" />
                        ) : (
                          <Lock className="w-3.5 h-3.5" />
                        )}
                        <span>{t('settings.save_password')}</span>
                      </button>
                    </div>
                  </form>
                </div>

                <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4">
                  <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2 font-interface">
                    <ShieldCheck className="w-4 h-4 text-accent" />
                    <span>{t('settings.sessions_security')}</span>
                  </h3>
                  <div className="space-y-3 text-xs">
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-text-3">{t('settings.enforce_https')}</span>
                      <span className={`font-bold ${systemSettings.enforce_https ? 'text-severity-ok' : 'text-severity-warning'}`}>
                        {systemSettings.enforce_https ? t('settings.active') : t('settings.inactive')}
                      </span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-text-3">{t('settings.jwt_signature')}</span>
                      <span className="font-mono text-text-1 font-semibold">{systemSettings.jwt_algorithm}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-text-3">{t('settings.access_ttl')}</span>
                      <span className="font-mono text-text-1 font-semibold">{formatDuration(systemSettings.jwt_access_token_ttl)}</span>
                    </div>
                    <div className="flex justify-between items-center py-1">
                      <span className="text-text-3">{t('settings.refresh_ttl')}</span>
                      <span className="font-mono text-text-1 font-semibold">{formatDuration(systemSettings.jwt_refresh_token_ttl)}</span>
                    </div>
                  </div>
                </div>

                <div className="p-5 border border-border rounded-xl bg-surface shadow space-y-4 md:col-span-2">
                  <h3 className="text-xs font-bold text-text-1 uppercase tracking-wider flex items-center gap-2 border-b border-border pb-2 font-interface">
                    <Database className="w-4 h-4 text-accent" />
                    <span>{t('settings.master_specs')}</span>
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-xs">
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-text-3">{t('settings.listen_host')}</span>
                      <span className="font-mono text-text-1 font-semibold">{systemSettings.host}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-text-3">{t('settings.listen_port')}</span>
                      <span className="font-mono text-text-1 font-semibold">{systemSettings.port}</span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-text-3">{t('settings.debug_mode')}</span>
                      <span className={`font-semibold ${systemSettings.debug ? 'text-severity-warning' : 'text-severity-ok'}`}>
                        {systemSettings.debug ? t('settings.debug_active') : t('settings.inactive')}
                      </span>
                    </div>
                    <div className="flex justify-between items-center py-1 border-b border-border/40">
                      <span className="text-text-3">{t('settings.heartbeat_uptime')}</span>
                      <span className="font-mono text-text-1 font-semibold">{systemSettings.heartbeat_interval}s</span>
                    </div>
                    <div className="flex justify-between items-start py-1 border-b border-border/40 sm:col-span-2">
                      <span className="text-text-3 shrink-0 mr-4">{t('settings.sqlite_db')}</span>
                      <span className="font-mono text-text-2 break-all text-right font-medium select-all" title={systemSettings.database_path}>
                        {systemSettings.database_path || '—'}
                      </span>
                    </div>
                    <div className="flex justify-between items-start py-1 sm:col-span-2">
                      <span className="text-text-3 shrink-0 mr-4">{t('settings.external_url')}</span>
                      <span className="font-mono text-text-2 break-all text-right font-medium select-all" title={systemSettings.master_url}>
                        {systemSettings.master_url || '—'}
                      </span>
                    </div>
                  </div>
                </div>

              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
