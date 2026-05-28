import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { useLocale } from '../../i18n';

interface InlineErrorProps {
  message?: string;
  details?: string;
  onRetry?: () => void;
}

export const InlineError: React.FC<InlineErrorProps> = ({
  message,
  details,
  onRetry,
}) => {
  const { t } = useLocale();

  return (
    <div className="flex flex-col items-center justify-center p-6 bg-surface-0 border border-danger/10 rounded-lg text-center gap-3 w-full animate-fade-in">
      <div className="flex items-center gap-2 text-danger">
        <AlertCircle size={20} />
        <span className="text-sm font-medium">
          {message || t('error.load_data')}
        </span>
      </div>
      {details && (
        <span className="text-xs text-ink-muted select-all">
          {details}
        </span>
      )}
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn btn-secondary text-xs flex items-center gap-1.5 py-1 px-3 mt-1"
        >
          <RefreshCw size={12} />
          {t('error.retry')}
        </button>
      )}
    </div>
  );
};
