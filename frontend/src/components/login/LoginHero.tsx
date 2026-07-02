import React from 'react';
import { ShieldAlert, Cpu, Activity, Terminal as TerminalIcon } from 'lucide-react';
import { useLocale } from '../../i18n';
import { ParticleCanvas } from './ParticleCanvas';
import { BootLogs } from './BootLogs';

export const LoginHero: React.FC = () => {
  const { t } = useLocale();

  return (
    <div className="hidden lg:flex lg:w-1/2 xl:w-3/5 bg-gradient-to-br from-surface-2 to-surface-3 border-r border-border flex-col p-12 justify-between relative overflow-hidden shrink-0">
      <ParticleCanvas />

      <div className="z-10 flex items-center gap-3">
        <div className="w-10 h-10 border border-accent/20 bg-accent/5 rounded-lg flex items-center justify-center shadow-lg">
          <ShieldAlert className="w-5 h-5 text-accent animate-pulse" />
        </div>
        <div>
          <div className="font-serif text-lg font-bold text-text-1 tracking-wide">Vigile</div>
          <div className="text-[8px] font-extrabold text-accent uppercase tracking-widest mt-0.5 font-interface">
            {t('login.brand_subtitle')}
          </div>
        </div>
      </div>

      <div className="z-10 max-w-lg my-auto space-y-8 animate-fade-in">
        <div>
          <span className="text-[9px] font-extrabold text-accent uppercase tracking-widest bg-accent-muted px-2 py-0.5 border border-accent/15 rounded font-interface">
            {t('login.badge_secure_access')}
          </span>
          <h1 className="font-serif text-3xl font-bold text-text-1 tracking-wide mt-3 leading-snug">
            {t('login.hero_title')}
          </h1>
          <p className="text-xs text-text-2 mt-3 leading-relaxed font-sans">
            {t('login.hero_description')}
          </p>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="bg-surface border border-border p-3 rounded-lg flex flex-col gap-1" title={t('login.feature_audit_tooltip')}>
            <span className="text-[8px] font-extrabold text-text-3 uppercase tracking-wider flex items-center gap-1 font-interface">
              <Activity className="w-2.5 h-2.5 text-accent" /> {t('login.feature_audit')}
            </span>
            <span className="text-xs font-bold text-severity-ok font-interface">{t('login.feature_audit_value')}</span>
          </div>
          <div className="bg-surface border border-border p-3 rounded-lg flex flex-col gap-1" title={t('login.feature_encryption_tooltip')}>
            <span className="text-[8px] font-extrabold text-text-3 uppercase tracking-wider flex items-center gap-1 font-interface">
              <Cpu className="w-2.5 h-2.5 text-accent" /> {t('login.feature_encryption')}
            </span>
            <span className="text-xs font-bold text-text-1 font-interface font-mono">{t('login.feature_encryption_value')}</span>
          </div>
          <div className="bg-surface border border-border p-3 rounded-lg flex flex-col gap-1" title={t('login.feature_websocket_tooltip')}>
            <span className="text-[8px] font-extrabold text-text-3 uppercase tracking-wider flex items-center gap-1 font-interface">
              <TerminalIcon className="w-2.5 h-2.5 text-accent" /> {t('login.feature_websocket')}
            </span>
            <span className="text-xs font-bold text-accent font-interface">{t('login.feature_websocket_value')}</span>
          </div>
        </div>
      </div>

      <div className="z-10">
        <BootLogs />
      </div>
    </div>
  );
};
