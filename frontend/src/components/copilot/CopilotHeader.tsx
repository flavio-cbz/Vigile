import React from 'react';
import { useLocale } from '../../i18n';
import { X, Sparkles, Server } from 'lucide-react';

interface CopilotHeaderProps {
  nodeName?: string;
  onClose: () => void;
}

export const CopilotHeader: React.FC<CopilotHeaderProps> = ({
  nodeName,
  onClose,
}) => {
  const { t } = useLocale();
  return (
    <div className="h-12 border-b border-border flex items-center justify-between px-4 shrink-0 font-interface bg-surface select-none">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded bg-accent/10 flex items-center justify-center border border-accent/20">
          <Sparkles className="w-3.5 h-3.5 text-accent animate-pulse" />
        </div>
        <span id="copilot-title" className="font-bold text-xs tracking-wider uppercase text-text-1">
          {t('copilot.title')}
        </span>

        {nodeName && (
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-2 border border-border text-[9px] font-bold text-text-2 uppercase tracking-wide">
            <Server className="w-2.5 h-2.5 text-accent" />
            <span className="truncate max-w-[80px]">{nodeName}</span>
          </div>
        )}
      </div>

      <button
        onClick={onClose}
        className="p-1 rounded hover:bg-surface-2 text-text-3 hover:text-text-1 cursor-pointer transition-colors"
        title={t("copilot.close_tooltip")}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};
