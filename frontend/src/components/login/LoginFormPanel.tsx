import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { useLocale } from '../../i18n';
import { ParticleCanvas } from './ParticleCanvas';
import { LoginForm } from '../auth/LoginForm';
import { ChangePasswordForm } from '../auth/ChangePasswordForm';

interface LoginFormPanelProps {
  mustChangePassword: boolean;
  isLoading: boolean;
  error: string | null;
  onLoginSubmit: (username: string, password: string) => Promise<void>;
  onDemoLogin: () => void;
  onPasswordChangeSubmit: (newPassword: string, confirmPassword: string) => Promise<void>;
  onCancelChangePassword: () => void;
}

export const LoginFormPanel: React.FC<LoginFormPanelProps> = ({
  mustChangePassword,
  isLoading,
  error,
  onLoginSubmit,
  onDemoLogin,
  onPasswordChangeSubmit,
  onCancelChangePassword,
}) => {
  const { t } = useLocale();

  const formatError = (msg: string): string => {
    try {
      const parsed = JSON.parse(msg) as { detail?: string };
      return typeof parsed?.detail === 'string' ? parsed.detail : msg;
    } catch {
      return msg;
    }
  };

  return (
    <div className="w-full lg:w-1/2 xl:w-2/5 flex items-center justify-center p-6 sm:p-12 bg-bg relative overflow-hidden shrink-0">
      <div className="absolute inset-0 block lg:hidden">
        <ParticleCanvas />
      </div>

      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-accent-muted rounded-full filter blur-[100px] opacity-40 pointer-events-none" />

      <div className="w-full max-w-sm border border-border rounded-xl bg-surface p-8 relative animate-fade-in z-10 shadow-2xl">
        <div className="flex flex-col items-center mb-8 text-center">
          <div className="w-12 h-12 border border-accent/20 bg-accent-muted rounded-xl flex items-center justify-center mb-3 shadow lg:hidden">
            <ShieldAlert className="w-6 h-6 text-accent animate-pulse" />
          </div>
          <h2 className="font-serif text-xl font-bold text-text-1 tracking-wide">
            {mustChangePassword ? t('login.form_title_change_password') : t('login.form_title')}
          </h2>
          <p className="text-[9px] font-extrabold text-accent uppercase tracking-widest mt-1.5 font-interface">
            {t('login.form_subtitle')}
          </p>
        </div>

        {error && (
          <div className="mb-5 p-3.5 rounded-lg bg-severity-critical/10 border border-severity-critical/20 text-severity-critical text-xs animate-fade-in font-semibold flex items-start gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-severity-critical mt-1 animate-pulse shrink-0" />
            <span>{formatError(error)}</span>
          </div>
        )}

        {!mustChangePassword ? (
          <LoginForm onSubmit={onLoginSubmit} loading={isLoading} onDemoLogin={onDemoLogin} />
        ) : (
          <ChangePasswordForm
            loading={isLoading}
            onSubmit={onPasswordChangeSubmit}
            onCancel={onCancelChangePassword}
          />
        )}

        <div className="text-center text-[8px] text-text-3 mt-8 select-none tracking-widest font-mono">
          {t('login.footer_version')}
        </div>
      </div>
    </div>
  );
};
