import React, { useState } from 'react';
import { User, Key, Lock, RefreshCw, Palette } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useUiStore, type ThemeKey } from '../../store/uiStore';
import { useLocale } from '../../i18n';
import { themes } from '../../design/themes';
import { api } from '../../hooks/useApi';

type Feedback = { type: 'success' | 'error'; msg: string };

export const ProfileSettingsTab: React.FC = () => {
  const { t, locale, setLocale } = useLocale();
  const { user, logout } = useAuthStore();
  const { theme, setTheme } = useUiStore();
  const availableThemes = Object.keys(themes) as ThemeKey[];

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordFeedback, setPasswordFeedback] = useState<Feedback | null>(null);

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

  return (
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
  );
};
