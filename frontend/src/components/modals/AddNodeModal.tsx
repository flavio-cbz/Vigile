import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  X,
  Plus,
  Copy,
  Check,
  RefreshCw,
  Terminal,
  Clock,
  AlertTriangle,
} from 'lucide-react';
import { useNodeStore, type Node } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';
import { api } from '../../hooks/useApi';
import { useLocale } from '../../i18n';

interface AddNodeModalProps {
  onClose: () => void;
}

interface JoinResponse {
  node_id: string;
  token: string;
  curl_command: string;
  expires_in: number;
}

const REFRESH_THRESHOLD_SEC = 30;
const POLL_INTERVAL_MS = 5000;
const ENROLLMENT_AUTO_CLOSE_MS = 2500;
const COPY_FEEDBACK_MS = 2000;
const TICK_INTERVAL_MS = 1000;


export const AddNodeModal = ({ onClose }: AddNodeModalProps) => {
  const { t } = useLocale();
  const [nodeName, setNodeName] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [joinData, setJoinData] = useState<JoinResponse | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingName, setPendingName] = useState<string | null>(null);
  const closeTimerRef = useRef<number | null>(null);

  const addToast = useToastStore((s) => s.addToast);

  // Refs for callbacks used inside the polling interval so the interval is
  // not recreated on every parent render.
  const onCloseRef = useRef(onClose);
  const addToastRef = useRef(addToast);
  const tRef = useRef(t);

  useEffect(() => {
    onCloseRef.current = onClose;
    addToastRef.current = addToast;
    tRef.current = t;
  });

  // ---- Token generation ----
  const generate = useCallback(async () => {
    if (!nodeName.trim() || isGenerating) return;
    setIsGenerating(true);
    setEnrollError(null);
    try {
      const data = await api<JoinResponse>('/api/nodes/generate-join', {
        method: 'POST',
        body: JSON.stringify({ name: nodeName }),
      });
      if (data) {
        setJoinData(data);
        setSecondsLeft(Math.max(0, Math.floor(data.expires_in)));
        setPendingName(nodeName);
        setNodeName('');
        useNodeStore.getState().fetchNodes();
      }
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsGenerating(false);
    }
  }, [nodeName, isGenerating]);

  const handleGenerateJoin = (e: React.FormEvent) => {
    e.preventDefault();
    void generate();
  };

  // ---- Countdown ticker ----
  useEffect(() => {
    if (!joinData || secondsLeft === null) return;
    if (secondsLeft <= 0) return;
    const id = window.setInterval(() => {
      setSecondsLeft((prev) => (prev === null ? null : Math.max(0, prev - 1)));
    }, TICK_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [joinData, secondsLeft]);

  // ---- Enrollment polling ----
  useEffect(() => {
    if (!joinData || !joinData.node_id || isEnrolled) return;

    const intervalId = setInterval(async () => {
      try {
        const nodes = await api<Node[]>('/api/nodes', { skipToast: true });
        if (nodes) {
          const enrolledNode = nodes.find((n) => n.id === joinData.node_id);
          if (enrolledNode && enrolledNode.online) {
            setIsEnrolled(true);
            clearInterval(intervalId);
            addToastRef.current('success', tRef.current('add_node.success'), tRef.current('add_node.success'));
            useNodeStore.getState().fetchNodes();
            closeTimerRef.current = window.setTimeout(() => {
              onCloseRef.current();
            }, ENROLLMENT_AUTO_CLOSE_MS);
          }
        }
      } catch (err) {
        console.error('Error polling node enrollment:', err);
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, [joinData, isEnrolled]);

  // ---- Cleanup ----
  useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  const [activeOS, setActiveOS] = useState<'linux_mac' | 'windows'>('linux_mac');

  // ---- Clipboard copy ----
  const windowsCommand = useMemo(() => {
    if (!joinData) return '';
    // Extract base URL of the master from the curl command or request context.
    // Example curl: curl -sSL http://localhost:8000/api/nodes/kickstart.sh | sudo sh -s -- --token TOKEN --master MASTER
    // Let's parse master_url or generate dynamic command using the token
    const token = joinData.token;
    // Fallback to extraction from curl_command if master_url isn't easily parsed
    const match = joinData.curl_command.match(/--master\s+([^\s]+)/);
    const masterUrl = match ? match[1] : 'http://localhost:8000';
    return `Invoke-WebRequest -Uri "${masterUrl}/api/nodes/kickstart.ps1" -OutFile kickstart.ps1\n.\\kickstart.ps1 -Token ${token} -Master ${masterUrl}`;
  }, [joinData]);

  const handleCopy = useCallback(async () => {
    const textToCopy = activeOS === 'windows' ? windowsCommand : (joinData?.curl_command || '');
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
    } catch {
      // Clipboard can fail in non-secure contexts; fall back to a hidden textarea.
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
      } catch {
        // give up silently
      } finally {
        document.body.removeChild(ta);
      }
    }
  }, [joinData, activeOS, windowsCommand]);

  // ---- Manual refresh: re-issue token with the same name ----
  const handleRefresh = useCallback(async () => {
    if (!joinData || refreshing) return;
    setRefreshing(true);
    setEnrollError(null);
    try {
      // nodeName is cleared after first submit, so re-use the name we cached
      // in pendingName. We never display the raw token — only the derived
      // command goes to the clipboard.
      const refreshName = pendingName || `${t('add_node.title')}-${Date.now()}`;
      const data = await api<JoinResponse>('/api/nodes/generate-join', {
        method: 'POST',
        body: JSON.stringify({ name: refreshName }),
      });
      if (data) {
        setJoinData(data);
        setSecondsLeft(Math.max(0, Math.floor(data.expires_in)));
        setIsEnrolled(false);
      }
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  }, [joinData, pendingName, refreshing, t]);

  // ---- Derived UI flags ----
  const expired = joinData !== null && secondsLeft !== null && secondsLeft <= 0;
  const expiringSoon = joinData !== null
    && secondsLeft !== null
    && secondsLeft > 0
    && secondsLeft <= REFRESH_THRESHOLD_SEC;

  const countdownLabel = useMemo(() => {
    if (secondsLeft === null) return '';
    if (secondsLeft <= 0) return t('add_node.token_expired');
    const m = Math.floor(secondsLeft / 60);
    const s = secondsLeft % 60;
    if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
    return `${s}s`;
  }, [secondsLeft, t]);

  return (
    <div
      className="fixed inset-0 bg-black/85 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-surface-0 border border-border p-6 rounded-xl shadow-2xl space-y-5 animate-fade-up relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink cursor-pointer"
          aria-label={t('common.close')}
        >
          <X className="w-4 h-4" />
        </button>

        <div>
          <h3 className="text-sm font-bold text-ink-primary uppercase tracking-wider flex items-center gap-2">
            <Plus className="w-4 h-4 text-accent-primary" />
            <span>{t('add_node.title')}</span>
          </h3>
          <p className="text-[0.625rem] text-ink-secondary mt-1 leading-relaxed">
            Créez une clé d'accès unique pour connecter un nouveau serveur à la console Vigile.
          </p>
        </div>

        {enrollError && (
          <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-[0.625rem] font-medium leading-relaxed">
            {enrollError}
          </div>
        )}

        {isEnrolled && (
          <div className="p-3 rounded-lg bg-success-subtle border border-success/20 text-success text-xs font-semibold text-center animate-pulse">
            🎉 {t('add_node.success')}
          </div>
        )}

        {!joinData ? (
          <form onSubmit={handleGenerateJoin} className="space-y-3">
            <div className="space-y-1">
              <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
                {t('add_node.name_label')}
              </label>
              <input
                type="text"
                required
                value={nodeName}
                onChange={(e) => setNodeName(e.target.value)}
                placeholder={t('add_node.name_placeholder')}
                className="input"
                autoFocus
              />
            </div>

            <button
              type="submit"
              disabled={isGenerating || !nodeName.trim()}
              className="btn btn-primary w-full py-2.5"
            >
              {isGenerating ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Terminal className="w-3.5 h-3.5" />
                  <span>{t('add_node.generate_token')}</span>
                </>
              )}
            </button>
          </form>
        ) : (
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
                <div
                  className={[
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[0.5625rem] font-mono font-semibold border',
                    expired
                      ? 'bg-danger-subtle border-danger/30 text-danger'
                      : expiringSoon
                        ? 'bg-warning-subtle border-warning/30 text-warning'
                        : 'bg-surface-1 border-border text-ink-secondary',
                  ].join(' ')}
                  title={t('add_node.expires_in_title')}
                >
                  {expired ? <AlertTriangle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                  <span>{countdownLabel}</span>
                </div>
              )}
            </div>

            {/* OS Selection Tabs */}
            <div className="flex border-b border-border">
              <button
                type="button"
                onClick={() => setActiveOS('linux_mac')}
                className={[
                  'px-4 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer',
                  activeOS === 'linux_mac'
                    ? 'border-accent-primary text-accent-primary'
                    : 'border-transparent text-ink-secondary hover:text-ink-primary'
                ].join(' ')}
              >
                {t('add_node.os_linux_mac')}
              </button>
              <button
                type="button"
                onClick={() => setActiveOS('windows')}
                className={[
                  'px-4 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer',
                  activeOS === 'windows'
                    ? 'border-accent-primary text-accent-primary'
                    : 'border-transparent text-ink-secondary hover:text-ink-primary'
                ].join(' ')}
              >
                {t('add_node.os_windows')}
              </button>
            </div>

            <div className="relative group">
              <div className="absolute top-0 left-0 right-0 h-6 bg-gradient-to-b from-surface-1 to-transparent pointer-events-none rounded-t-lg" />
              <div className="flex items-center gap-1.5 px-3 py-2 bg-surface-2 border border-border border-b-0 rounded-t-lg">
                <span className="w-2.5 h-2.5 rounded-full bg-danger/60" />
                <span className="w-2.5 h-2.5 rounded-full bg-warning/60" />
                <span className="w-2.5 h-2.5 rounded-full bg-success/60" />
                <span className="ml-2 text-[0.5625rem] font-mono text-ink-muted uppercase tracking-wider">
                  {activeOS === 'windows' ? 'powershell' : 'sh'}
                </span>
              </div>
              <pre
                className={[
                  'p-4 bg-[#08080d] border border-border border-t-0 rounded-b-lg overflow-x-auto',
                  'font-mono text-[0.6875rem] leading-relaxed text-ink-primary',
                  'whitespace-pre-wrap break-all select-all',
                  expired ? 'opacity-50' : '',
                ].join(' ')}
                aria-label={t('add_node.deploy_command_aria')}
              >
                {activeOS === 'windows' ? windowsCommand : joinData.curl_command}
              </pre>
            </div>

            <button
              type="button"
              onClick={handleCopy}
              disabled={expired}
              className={[
                'btn w-full py-3 text-sm font-semibold',
                copied ? 'btn-secondary' : 'btn-primary',
                expired ? 'opacity-50 cursor-not-allowed' : '',
              ].join(' ')}
            >
              {copied ? (
                <>
                  <Check className="w-4 h-4 text-success" />
                  <span>{t('chat.copied')}</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  <span>{t('add_node.copy_command')}</span>
                </>
              )}
            </button>

            <div
              className={[
                'p-2.5 rounded-lg border text-[0.625rem] leading-relaxed flex items-start gap-2',
                expired
                  ? 'bg-danger-subtle border-danger/20 text-danger'
                  : expiringSoon
                    ? 'bg-warning-subtle border-warning/20 text-warning'
                    : 'bg-surface-1 border-border text-ink-secondary',
              ].join(' ')}
            >
              {expired ? (
                <>
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <div className="flex-1">
                    <span>{t('add_node.token_expired_msg')}</span>
                    <button
                      type="button"
                      onClick={handleRefresh}
                      disabled={refreshing}
                      className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-2 border border-border text-ink-primary hover:border-accent-primary/40 cursor-pointer font-semibold"
                    >
                      <RefreshCw className={['w-3 h-3', refreshing ? 'animate-spin' : ''].join(' ')} />
                      <span>{t('add_node.refresh')}</span>
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <Clock className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>
                    {activeOS === 'windows' ? t('add_node.windows_privileges') : t('add_node.warning_privileges', { time: countdownLabel })}
                  </span>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
