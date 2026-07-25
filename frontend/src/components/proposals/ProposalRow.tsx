import React, { useState } from 'react';
import type { ActionProposal } from '../../store/uiStore';
import type { Node } from '../../store/nodeStore';
import { StatusDot } from '../primitives/StatusDot';
import { TimeAgo } from '../primitives/TimeAgo';
import { Check, X } from 'lucide-react';
import { formatDateTime } from '../../utils/formatTime';
import { useLocale } from '../../i18n';

export const ProposalRow: React.FC<{
  prop: ActionProposal;
  node: Node | undefined;
  isOperator: boolean;
  executing: boolean;
  handleRejectInit: (id: string) => void;
  setApprovingId: (id: string) => void;
  getStatusStyles: (status: string) => string;
}> = ({
  prop,
  node,
  isOperator,
  executing,
  handleRejectInit,
  setApprovingId,
  getStatusStyles,
}) => {
  const { t } = useLocale();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`p-5 border border-border rounded-xl bg-surface hover:border-border-strong flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm transition-all duration-200 ${isExpanded ? '!h-auto' : ''}`}
    >
      <div className="space-y-2 min-w-0 flex-1">
        <div className="flex items-center flex-wrap gap-2">
          <span className={`text-[8px] font-extrabold tracking-widest uppercase px-1.5 py-0.5 border rounded ${getStatusStyles(prop.status)}`}>
            {prop.status}
          </span>
          {node && (
            <div className="flex items-center gap-1 text-[10px] font-bold text-text-2 bg-surface-2 px-1.5 py-0.5 border border-border rounded">
              <StatusDot state={node.state} className="mr-0.5" />
              <span>{node.name}</span>
            </div>
          )}
          <span className="text-text-3 text-[10px] font-mono">
            {t('prop.created')} <TimeAgo timestamp={prop.created_at} />
          </span>
        </div>

        <h4 className="font-mono text-xs text-text-1 font-bold truncate">
          {t('prop.action')} : <span className="text-accent">{prop.action}</span>
          {Boolean(prop.params?.target) && (
            <> · {t('prop.target')} : <code className="text-text-2">{String(prop.params!.target)}</code></>
          )}
        </h4>

        <p className="text-text-2 text-xs font-sans leading-relaxed font-normal">
          {isExpanded ? prop.reasoning : (prop.reasoning && prop.reasoning.length > 70 ? `${prop.reasoning.substring(0, 70)}...` : prop.reasoning)}
          {prop.reasoning && prop.reasoning.length > 70 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1.5 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[10px]"
            >
              {isExpanded ? t('common.less') : t('common.more')}
            </button>
          )}
        </p>

        {Boolean(prop.params?.result) && (
          <div className="p-3 rounded bg-surface-2 border border-border font-mono text-[10px] text-text-2 leading-relaxed max-h-24 overflow-y-auto mt-2">
            Result: {String(prop.params!.result)}
          </div>
        )}
      </div>

      {prop.status === 'PENDING' && isOperator && (
        <div className="flex sm:flex-col gap-2 shrink-0 sm:w-28 font-interface">
          <button
            onClick={() => handleRejectInit(prop.id)}
            disabled={executing}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[9px] font-bold border border-severity-critical/20 hover:border-severity-critical/50 hover:bg-severity-critical/10 text-severity-critical/80 hover:text-severity-critical rounded cursor-pointer disabled:opacity-50 transition-colors"
          >
            <X className="w-3 h-3" />
            <span>{t('prop.btn.reject')}</span>
          </button>
          <button
            onClick={() => setApprovingId(prop.id)}
            disabled={executing}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[9px] font-bold bg-accent hover:bg-accent-hover text-text-1 rounded shadow cursor-pointer disabled:opacity-50 transition-colors"
          >
            <Check className="w-3 h-3" />
            <span>{t('prop.btn.approve')}</span>
          </button>
        </div>
      )}

      {prop.status === 'PENDING' && !isOperator && (
        <div className="text-[10px] text-text-3 italic font-sans shrink-0 sm:w-28 text-center py-2 border border-dashed border-border rounded">
          Droits requis
        </div>
      )}

      {prop.status !== 'PENDING' && (
        <div className="text-[10px] font-bold font-interface shrink-0 sm:w-36 text-right py-2 select-none">
          {prop.status === 'APPROVED' || prop.status === 'EXECUTED' ? (
            <div className="text-severity-ok flex items-center justify-end gap-1">
              <Check className="w-3.5 h-3.5" />
              <span>Exécuté le {formatDateTime(prop.executed_at || prop.updated_at)}</span>
            </div>
          ) : prop.status === 'FAILED' ? (
            <div className="text-severity-critical flex items-center justify-end gap-1">
              <span className="text-xs">⚠</span>
              <span>Échoué le {formatDateTime(prop.executed_at || prop.updated_at)}</span>
            </div>
          ) : (
            <div className="text-text-3 flex items-center justify-end gap-1">
              <X className="w-3.5 h-3.5" />
              <span>Rejeté le {formatDateTime(prop.updated_at)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
