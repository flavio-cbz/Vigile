import React, { useState } from 'react';
import { KeyRound, Loader2 } from 'lucide-react';
import { useLocale } from '../../i18n';

interface ChangePasswordFormProps {
  loading: boolean;
  onSubmit: (newPassword: string, confirmPassword: string) => Promise<void> | void;
  onCancel: () => void;
}

export const ChangePasswordForm: React.FC<ChangePasswordFormProps> = ({ loading, onSubmit, onCancel }) => {
  const { t } = useLocale();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    onSubmit(newPassword, confirmPassword);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 font-sans text-xs">
      <div className="mb-4 text-xs text-severity-warning bg-severity-warning/10 border border-severity-warning/20 p-3.5 rounded-lg font-medium flex items-start gap-2 leading-relaxed">
        <div className="w-1.5 h-1.5 rounded-full bg-severity-warning mt-1.5 animate-pulse shrink-0" />
        <span>{t('login.must_change_password_message')}</span>
      </div>

      <div className="space-y-1.5">
        <label className="block text-[10px] font-extrabold text-text-2 uppercase tracking-wider font-interface" htmlFor="newPassword">
          {t('login.new_password_label')}
        </label>
        <input
          id="newPassword"
          type="password"
          required
          disabled={loading}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder={t('login.new_password_placeholder')}
          className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
          autoFocus
        />
      </div>

      <div className="space-y-1.5">
        <label className="block text-[10px] font-extrabold text-text-2 uppercase tracking-wider font-interface" htmlFor="confirmPassword">
          {t('login.confirm_password_label')}
        </label>
        <input
          id="confirmPassword"
          type="password"
          required
          disabled={loading}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          placeholder={t('login.confirm_password_placeholder')}
          className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
        />
      </div>

      <div className="flex gap-3 mt-6">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 border border-border hover:border-border-strong px-4 py-2 text-[10px] font-bold font-interface uppercase tracking-wider rounded cursor-pointer transition-colors"
        >
          {t('login.cancel_button')}
        </button>
        <button
          type="submit"
          disabled={loading || !newPassword.trim() || !confirmPassword.trim()}
          className="flex-1 bg-accent hover:bg-accent-hover text-text-1 px-4 py-2 text-[10px] font-bold font-interface uppercase tracking-wider rounded flex items-center justify-center gap-1.5 cursor-pointer shadow-lg shadow-accent/15 transition-all"
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <>
              <KeyRound className="w-3.5 h-3.5" />
              <span>{t('login.validate_button')}</span>
            </>
          )}
        </button>
      </div>
    </form>
  );
};
