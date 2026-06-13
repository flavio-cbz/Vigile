import { useEffect, useRef } from 'react';
import { X, CheckCircle2, XCircle, Info, AlertTriangle } from 'lucide-react';
import { useToastStore, type ToastType, type Toast } from '../../store/useToastStore';

const toastStyles = `
  @keyframes toastSlideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
  @keyframes toastFadeOut {
    from { opacity: 1; }
    to { opacity: 0; transform: translateX(20px); }
  }
  .toast-enter {
    animation: toastSlideIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) both;
  }
  .toast-exit {
    animation: toastFadeOut 0.25s ease-in both;
  }
`;

const iconMap: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

const typeToColors: Record<ToastType, { text: string }> = {
  success: { text: 'text-severity-ok' },
  error: { text: 'text-severity-critical' },
  info: { text: 'text-accent' },
  warning: { text: 'text-severity-warning' },
};

function ToastItem({ toast }: { toast: Toast }) {
  const removeToast = useToastStore((s) => s.removeToast);
  const Icon = iconMap[toast.type];
  const colors = typeToColors[toast.type];

  return (
    <div
      className={`flex items-start gap-3 p-4 bg-surface border border-border rounded-lg shadow-2xl min-w-[320px] max-w-sm relative overflow-hidden ${
        toast.exiting ? 'toast-exit' : 'toast-enter'
      }`}
      role="alert"
    >
      <div className={`flex-shrink-0 mt-0.5 ${colors.text}`}>
        <Icon size={18} aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0 font-sans text-xs">
        <p className="text-sm font-bold text-text-1 font-interface uppercase tracking-wide">{toast.title}</p>
        {toast.message && (
          <p className="text-text-2 mt-1 leading-relaxed">{toast.message}</p>
        )}
      </div>
      <button
        onClick={() => removeToast(toast.id)}
        className="flex-shrink-0 text-text-3 hover:text-text-1 transition-colors duration-150 p-0.5 rounded hover:bg-surface-2 cursor-pointer"
        aria-label="Fermer"
      >
        <X size={16} />
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const injectedRef = useRef(false);

  useEffect(() => {
    if (injectedRef.current) return;
    injectedRef.current = true;
    const el = document.createElement('style');
    el.textContent = toastStyles;
    document.head.appendChild(el);
    return () => {
      el.remove();
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-3" aria-live="polite" role="status">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
