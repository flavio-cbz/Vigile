import React from 'react';
import { AlertCircle, CheckCircle2, AlertTriangle, Info } from 'lucide-react';

type BannerVariant = 'info' | 'success' | 'warning' | 'error';

interface BannerProps {
  variant: BannerVariant;
  title: string;
  message?: string;
  action?: { label: string; onClick: () => void };
}

const VARIANT_STYLES: Record<BannerVariant, { container: string; icon: string; Icon: React.FC<{ className?: string }> }> = {
  info: {
    container: 'bg-blue-500/10 border-blue-500/20',
    icon: 'text-blue-400',
    Icon: Info,
  },
  success: {
    container: 'bg-emerald-500/10 border-emerald-500/20',
    icon: 'text-emerald-400',
    Icon: CheckCircle2,
  },
  warning: {
    container: 'bg-amber-500/10 border-amber-500/20',
    icon: 'text-amber-500',
    Icon: AlertTriangle,
  },
  error: {
    container: 'bg-red-500/10 border-red-500/20',
    icon: 'text-red-400',
    Icon: AlertCircle,
  },
};

export const Banner: React.FC<BannerProps> = ({ variant, title, message, action }) => {
  const styles = VARIANT_STYLES[variant];
  const { Icon } = styles;

  return (
    <div
      className={`flex flex-col items-center justify-center py-12 rounded-xl border text-center px-6 gap-4 ${styles.container}`}
    >
      <div className={`w-12 h-12 rounded-full flex items-center justify-center ${styles.container}`}>
        <Icon className={`w-6 h-6 ${styles.icon}`} />
      </div>
      <div className="max-w-md">
        <h3 className="text-base font-bold text-text-1 font-mono">{title}</h3>
        {message && (
          <p className="text-xs text-text-3 mt-1 leading-relaxed">{message}</p>
        )}
      </div>
      {action && (
        <button
          onClick={action.onClick}
          className="px-5 py-2 text-xs font-mono font-bold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer shadow-lg"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};
