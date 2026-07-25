import React from 'react';
import { useLocale } from '../../i18n';
import { AlertCircle } from 'lucide-react';

interface CopilotPendingTickerProps {
  count: number;
  highestRiskLabel?: string;
  onFocusFirstPending: () => void;
}

export const CopilotPendingTicker: React.FC<CopilotPendingTickerProps> = ({
  count,
  highestRiskLabel,
  onFocusFirstPending,
}) => {
  const { t } = useLocale();
  if (count <= 0) return null;

  return (
    <button
      onClick={onFocusFirstPending}
      className="cp-pending-ticker w-full flex items-center gap-2 px-3 py-1.5 border-b border-severity-critical/15 text-left transition-colors hover:bg-severity-critical/10"
      aria-live="polite"
    >
      <AlertCircle className="w-3.5 h-3.5 text-severity-critical shrink-0" />
      <span className="text-[11px] font-bold text-severity-critical flex-1 min-w-0">
        {t('copilot.pending_count', { n: count })}
      </span>
      {highestRiskLabel && (
        <span className="text-[9px] uppercase tracking-wider font-mono text-text-2 border border-border rounded px-1.5 py-0.5 shrink-0">
          {highestRiskLabel}
        </span>
      )}
      <span className="text-[10px] text-text-3 hover:text-text-1 transition-colors shrink-0">
        {t('copilot.review')} →
      </span>
    </button>
  );
};
