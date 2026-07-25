import React from 'react';
import { useLocale } from '../../i18n';

interface ProposalRejectModalProps {
  reason: string;
  onChange: (reason: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export const ProposalRejectModal: React.FC<ProposalRejectModalProps> = ({
  reason,
  onChange,
  onCancel,
  onConfirm,
}) => {
  const { t } = useLocale();
  const canSubmit = reason.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs select-none animate-fade-in">
      <div className="w-full max-w-md p-6 bg-surface border border-border rounded-xl shadow-2xl space-y-4">
        <div>
          <h3 className="text-sm font-bold text-text-1 font-interface uppercase tracking-wider">
            {t('dash.reject_reason_title')}
          </h3>
          <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
            {t('dash.reject_reason_description')}
          </p>
        </div>

        <textarea
          value={reason}
          onChange={(e) => onChange(e.target.value)}
          placeholder={t('dash.reject_reason_placeholder')}
          className="w-full h-24 bg-surface-2 border border-border focus:border-accent/40 rounded-lg p-3 text-xs text-text-1 placeholder:text-text-3 focus:outline-none resize-none font-sans"
          autoFocus
        />

        <div className="flex justify-end gap-2.5 font-interface text-[10px] font-bold">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 border border-border hover:border-border-strong text-text-2 rounded-lg cursor-pointer transition-colors"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={onConfirm}
            className="px-4 py-2 bg-severity-critical text-text-1 hover:bg-severity-critical/80 rounded-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {t('dash.reject_confirm')}
          </button>
        </div>
      </div>
    </div>
  );
};
