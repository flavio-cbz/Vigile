import React from 'react';
import { useLocale } from '../../i18n';
import { X, Sparkles, Server, Cpu } from 'lucide-react';
import { StatusDot } from '../primitives/StatusDot';

interface CopilotHeaderProps {
  nodeName?: string;
  nodeOnline?: boolean;
  nodeId?: string | null;
  model?: string;
  onClose: () => void;
  pendingCount?: number;
}

export const CopilotHeader: React.FC<CopilotHeaderProps> = ({
  nodeName,
  nodeOnline,
  nodeId,
  model,
  onClose,
  pendingCount = 0,
}) => {
  const { t } = useLocale();
  return (
    <header
      className="cp-glass shrink-0 flex items-center justify-between px-4 select-none"
      style={{ height: 'var(--copilot-header-height)' }}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <div className="w-7 h-7 rounded-lg bg-accent-info/12 border border-accent-info/25 flex items-center justify-center shrink-0">
          <Sparkles className="w-4 h-4 text-accent-info-strong" />
        </div>
        <div className="flex flex-col min-w-0">
          <h2
            id="copilot-title"
            className="font-bold text-[11px] tracking-widest uppercase text-text-1 font-interface leading-tight truncate flex items-center gap-1.5"
          >
            {t('copilot.title')}
            {pendingCount > 0 && (
              <span className="bg-severity-critical/15 text-severity-critical rounded-full text-[9px] px-1.5 leading-tight font-mono">
                {pendingCount}
              </span>
            )}
          </h2>
          <div className="flex items-center gap-1.5 min-w-0">
            {nodeName && nodeId ? (
              <div className="flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-surface-2/70 border border-border text-[9.5px] font-bold text-text-2 leading-none">
                <StatusDot state={nodeOnline ? 'connected' : 'lost'} />
                <Server className="w-2.5 h-2.5 text-accent-info-strong" />
                <span className="truncate max-w-[100px]">{nodeName}</span>
              </div>
            ) : (
              <span className="text-[9.5px] text-text-3 uppercase tracking-wider font-semibold">
                {t('copilot.scope_global')}
              </span>
            )}
            {model && (
              <span className="flex items-center gap-1 text-[9.5px] text-text-3 bg-surface-3/40 border border-border rounded px-1.5 py-0.5 font-mono truncate max-w-[120px]">
                <Cpu className="w-2.5 h-2.5" />
                {model}
              </span>
            )}
          </div>
        </div>
      </div>

      <button
        onClick={onClose}
        className="p-1.5 rounded-md hover:bg-surface-3/60 text-text-3 hover:text-text-1 cursor-pointer transition-colors shrink-0"
        title={t('copilot.close_tooltip')}
        aria-label={t('copilot.close_tooltip')}
      >
        <X className="w-4 h-4" />
      </button>
    </header>
  );
};
