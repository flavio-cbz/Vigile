import { useState, useEffect, useMemo, useCallback } from 'react';
import { Copy, Check, RefreshCw, Clock, AlertTriangle } from 'lucide-react';
import { useLocale } from '../../i18n';
import type { JoinResponse } from './AddNodeModal';

const REFRESH_THRESHOLD_SEC = 30;
const COPY_FEEDBACK_MS = 2000;
const TICK_INTERVAL_MS = 1000;

interface JoinTokenDisplayProps {
  joinData: JoinResponse;
  isEnrolled: boolean;
  onRefresh: () => Promise<void>;
  refreshing: boolean;
}

export const JoinTokenDisplay = ({
  joinData,
  isEnrolled,
  onRefresh,
  refreshing,
}: JoinTokenDisplayProps) => {
  const { t } = useLocale();
  const [activeOS, setActiveOS] = useState<'linux_mac' | 'windows'>('linux_mac');
  const [copied, setCopied] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(
    Math.max(0, Math.floor(joinData.expires_in)),
  );

  useEffect(() => {
    setSecondsLeft(Math.max(0, Math.floor(joinData.expires_in)));
  }, [joinData]);
  useEffect(() => {
    if (secondsLeft === null || secondsLeft <= 0) return;
    const id = window.setInterval(
      () => setSecondsLeft((prev) => (prev === null ? null : Math.max(0, prev - 1))),
      TICK_INTERVAL_MS,
    );
    return () => window.clearInterval(id);
  }, [secondsLeft]);

  const windowsCommand = useMemo(() => {
    const match = joinData.curl_command.match(/--master\s+([^\s]+)/);
    const masterUrl = match ? match[1] : 'http://localhost:8000';
    return `Invoke-WebRequest -Uri "${masterUrl}/api/nodes/kickstart.ps1" -OutFile kickstart.ps1\n.\\kickstart.ps1 -Token ${joinData.token} -Master ${masterUrl}`;
  }, [joinData]);

  const handleCopy = useCallback(async () => {
    const textToCopy = activeOS === 'windows' ? windowsCommand : joinData.curl_command;
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = textToCopy;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        window.setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
      } catch { /* silent */ } finally { document.body.removeChild(ta); }
    }
  }, [joinData, activeOS, windowsCommand]);

  const expired = secondsLeft !== null && secondsLeft <= 0;
  const expiringSoon = secondsLeft !== null && secondsLeft > 0 && secondsLeft <= REFRESH_THRESHOLD_SEC;
  const countdownLabel = useMemo(() => {
    if (secondsLeft === null) return '';
    if (secondsLeft <= 0) return t('add_node.token_expired');
    const m = Math.floor(secondsLeft / 60);
    const s = secondsLeft % 60;
    return m > 0 ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
  }, [secondsLeft, t]);

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {!isEnrolled ? (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-accent-subtle border border-accent-primary/20 rounded-full text-accent-primary text-[0.625rem] font-semibold">
            <RefreshCw className="w-3 h-3 animate-spin" />
            <span>{t('add_node.waiting')}</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-success-subtle border border-success/20 rounded-full text-success text-[0.625rem] font-semibold">
            <Check className="w-3 h-3" />
            <span>{t('add_node.success')}</span>
          </div>
        )}
        {secondsLeft !== null && (
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[0.5625rem] font-mono font-semibold border ${expired ? 'bg-danger-subtle border-danger/30 text-danger' : expiringSoon ? 'bg-warning-subtle border-warning/30 text-warning' : 'bg-surface-1 border-border text-ink-secondary'}`} title={t('add_node.expires_in_title')}>
            {expired ? <AlertTriangle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
            <span>{countdownLabel}</span>
          </div>
        )}
      </div>

      <div className="flex border-b border-border">
        <button type="button" onClick={() => setActiveOS('linux_mac')} className={['px-4 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer', activeOS === 'linux_mac' ? 'border-accent-primary text-accent-primary' : 'border-transparent text-ink-secondary hover:text-ink-primary'].join(' ')}>
          {t('add_node.os_linux_mac')}
        </button>
        <button type="button" onClick={() => setActiveOS('windows')} className={['px-4 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer', activeOS === 'windows' ? 'border-accent-primary text-accent-primary' : 'border-transparent text-ink-secondary hover:text-ink-primary'].join(' ')}>
          {t('add_node.os_windows')}
        </button>
      </div>

      <div className="relative group">
        <div className="absolute top-0 left-0 right-0 h-6 bg-gradient-to-b from-surface-1 to-transparent pointer-events-none rounded-t-lg" />
        <div className="flex items-center gap-1.5 px-3 py-2 bg-surface-2 border border-border border-b-0 rounded-t-lg">
          <span className="w-2.5 h-2.5 rounded-full bg-danger/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-warning/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-success/60" />
          <span className="ml-2 text-[0.5625rem] font-mono text-ink-muted uppercase tracking-wider">{activeOS === 'windows' ? 'powershell' : 'sh'}</span>
        </div>
        <pre className={['p-4 bg-surface-2 border border-border border-t-0 rounded-b-lg overflow-x-auto', 'font-mono text-[0.6875rem] leading-relaxed text-ink-primary', 'whitespace-pre-wrap break-all select-all', expired ? 'opacity-50' : ''].join(' ')} aria-label={t('add_node.deploy_command_aria')}>
          {activeOS === 'windows' ? windowsCommand : joinData.curl_command}
        </pre>
      </div>

      <button type="button" onClick={handleCopy} disabled={expired} className={['btn w-full py-3 text-sm font-semibold', copied ? 'btn-secondary' : 'btn-primary', expired ? 'opacity-50 cursor-not-allowed' : ''].join(' ')}>
        {copied ? <><Check className="w-4 h-4 text-success" /><span>{t('chat.copied')}</span></>
          : <><Copy className="w-4 h-4" /><span>{t('add_node.copy_command')}</span></>}
      </button>

      <div className={`p-2.5 rounded-lg border text-[0.625rem] leading-relaxed flex items-start gap-2 ${expired ? 'bg-danger-subtle border-danger/20 text-danger' : expiringSoon ? 'bg-warning-subtle border-warning/20 text-warning' : 'bg-surface-1 border-border text-ink-secondary'}`}>
        {expired ? (
          <>
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <div className="flex-1">
              <span>{t('add_node.token_expired_msg')}</span>
              <button type="button" onClick={onRefresh} disabled={refreshing} className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-2 border border-border text-ink-primary hover:border-accent-primary/40 cursor-pointer font-semibold">
                <RefreshCw className={['w-3 h-3', refreshing ? 'animate-spin' : ''].join(' ')} />
                <span>{t('add_node.refresh')}</span>
              </button>
            </div>
          </>
        ) : (
          <>
            <Clock className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>{activeOS === 'windows' ? t('add_node.windows_privileges') : t('add_node.warning_privileges', { time: countdownLabel })}</span>
          </>
        )}
      </div>
    </div>
  );
};
