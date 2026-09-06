import { useState, useCallback, useRef, useEffect } from 'react';
import { Globe, Loader2, X, CheckCircle, AlertTriangle, Clock } from 'lucide-react';
import type { ExternalAuthPopupProps, AuthState, StartCommandResponse } from './types';

const WINDOW_CHECK_MS = 1000;

export function ExternalAuthPopup({ context, config, title }: ExternalAuthPopupProps) {
  const [state, setState] = useState<AuthState>('idle');
  const popupRef = useRef<Window | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (typeof cleanupRef.current === 'function') {
      cleanupRef.current();
      cleanupRef.current = null;
    }
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const handleCancel = useCallback(() => {
    cleanup();
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.close();
    }
    popupRef.current = null;
    setState('cancelled');
    void context.api.fetch(config.cancel_command, { method: 'POST' }).catch(() => {});
  }, [cleanup, context.api, config.cancel_command]);

  const startWindowCheck = useCallback(() => {
    const check = () => {
      if (popupRef.current?.closed) {
        handleCancel();
        return;
      }
      timerRef.current = setTimeout(check, WINDOW_CHECK_MS);
    };
    timerRef.current = setTimeout(check, WINDOW_CHECK_MS);
  }, [handleCancel]);

  const handleStart = useCallback(async () => {
    setState('waiting');
    try {
      const response = await context.api.fetch<StartCommandResponse>(config.start_command, {
        method: 'POST',
      });
      const authUrl = response?.auth_url;
      if (!authUrl) {
        setState('error');
        return;
      }
      const { w, h } = config.popup_size;
      const popup = window.open(authUrl, 'External Auth', `width=${w},height=${h}`);
      popupRef.current = popup;
      startWindowCheck();

      if (context.subscribeStatus) {
        const unsub = context.subscribeStatus(config.status_channel, (data: Record<string, unknown>) => {
          const status = data.status as AuthState | undefined;
          if (status === 'success' || status === 'error' || status === 'timeout') {
            cleanup();
            if (popupRef.current && !popupRef.current.closed) {
              popupRef.current.close();
            }
            popupRef.current = null;
            setState(status);
          }
        });
        cleanupRef.current = unsub;
      }
    } catch {
      cleanup();
      setState('error');
    }
  }, [context, config, startWindowCheck, cleanup]);

  const handleRetry = useCallback(() => {
    setState('idle');
  }, []);

  const displayTitle = title ?? 'Authentification';

  if (state === 'idle') {
    return (
      <div className="flex flex-col gap-3 p-4 rounded-xl bg-surface-1 border border-border-strong/15">
        <span className="text-sm font-semibold text-text-1">{displayTitle}</span>
        <button
          type="button"
          onClick={handleStart}
          className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer"
        >
          <Globe className="w-4 h-4" />
          Connecter
        </button>
      </div>
    );
  }

  if (state === 'waiting') {
    return (
      <div className="flex flex-col gap-3 p-4 rounded-xl bg-surface-1 border border-border-strong/15">
        <span className="text-sm font-semibold text-text-1">{displayTitle}</span>
        <div className="flex items-center gap-2 text-xs text-text-3 font-mono">
          <Loader2 className="w-3.5 h-3.5 text-orange-400 animate-spin" />
          En attente de l&#39;authentification...
        </div>
        <button
          type="button"
          onClick={handleCancel}
          className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-zinc-800 hover:bg-zinc-700 text-text-2 rounded-lg transition-colors cursor-pointer"
        >
          <X className="w-4 h-4" />
          Annuler
        </button>
      </div>
    );
  }

  if (state === 'success') {
    return (
      <div className="flex flex-col gap-3 p-4 rounded-xl bg-surface-1 border border-border-strong/15">
        <div className="flex items-center gap-2 text-sm text-emerald-400 font-semibold">
          <CheckCircle className="w-4 h-4" />
          Connexion réussie
        </div>
        <button
          type="button"
          onClick={handleRetry}
          className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer"
        >
          <Globe className="w-4 h-4" />
          Reconnecter
        </button>
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="flex flex-col gap-3 p-4 rounded-xl bg-surface-1 border border-border-strong/15">
        <div className="flex items-center gap-2 text-sm text-red-400 font-semibold">
          <AlertTriangle className="w-4 h-4" />
          Erreur d&#39;authentification
        </div>
        <button
          type="button"
          onClick={handleRetry}
          className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer"
        >
          <Globe className="w-4 h-4" />
          Réessayer
        </button>
      </div>
    );
  }

  if (state === 'timeout') {
    return (
      <div className="flex flex-col gap-3 p-4 rounded-xl bg-surface-1 border border-border-strong/15">
        <div className="flex items-center gap-2 text-sm text-amber-400 font-semibold">
          <Clock className="w-4 h-4" />
          Délai d&#39;authentification expiré
        </div>
        <button
          type="button"
          onClick={handleRetry}
          className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer"
        >
          <Globe className="w-4 h-4" />
          Réessayer
        </button>
      </div>
    );
  }

  // cancelled
  return (
    <div className="flex flex-col gap-3 p-4 rounded-xl bg-surface-1 border border-border-strong/15">
      <div className="flex items-center gap-2 text-sm text-text-3 font-semibold">
        <X className="w-4 h-4" />
        Authentification annulée
      </div>
      <button
        type="button"
        onClick={handleRetry}
        className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer"
      >
        <Globe className="w-4 h-4" />
        Reconnecter
      </button>
    </div>
  );
}
