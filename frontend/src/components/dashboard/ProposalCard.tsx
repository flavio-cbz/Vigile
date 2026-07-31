import React, { useState } from 'react';
import type { ActionProposal } from '../../store/uiStore';
import { Check, X, ShieldAlert, AlertTriangle } from 'lucide-react';
import { usePermission } from '../../hooks/usePermission';
import { useLocale } from '../../i18n';
import { formatDateTime } from '../../utils/formatTime';


interface ProposalCardProps {
  proposal: ActionProposal;
  nodeName: string;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
  loading?: boolean;
  removing?: boolean;
}

export const ProposalCard: React.FC<ProposalCardProps> = ({
  proposal,
  nodeName,
  onApprove,
  onReject,
  loading = false,
  removing = false,
}) => {
  const { t } = useLocale();
  const { can } = usePermission();
  const [isExpanded, setIsExpanded] = useState(false);
  const isOperator = can('approve-action');

  const getRiskStyles = (risk: string) => {
    switch (risk.toLowerCase()) {
      case 'high':
      case 'critical':
        return 'bg-severity-critical/10 text-severity-critical border-severity-critical/20';
      case 'medium':
      case 'warning':
        return 'bg-severity-warning/10 text-severity-warning border-severity-warning/20';
      case 'low':
      case 'ok':
      default:
        return 'bg-severity-ok/10 text-severity-ok border-severity-ok/20';
    }
  };

  const getRiskLabel = (risk: string): string => {
    switch (risk.toLowerCase()) {
      case 'critical': return t('prop.risk_critical');
      case 'high': return t('prop.risk_high');
      case 'medium': return t('prop.risk_medium');
      case 'low': return t('prop.risk_low');
      default: return risk.toUpperCase();
    }
  };

  const parsedParams = typeof proposal.params === 'object' && proposal.params !== null ? proposal.params :
                       ('params_json' in proposal && typeof proposal.params_json === 'string' ? (() => {
                         try {
                           return JSON.parse(proposal.params_json as string) as Record<string, unknown>;
                         } catch {
                           return {};
                         }
                       })() : {}) as Record<string, unknown>;

  const displayTarget = proposal.target ||
                        (typeof parsedParams?.service === 'string' ? parsedParams.service : '') ||
                        (typeof parsedParams?.container_id === 'string' ? parsedParams.container_id : '') ||
                        (typeof parsedParams?.container === 'string' ? parsedParams.container : '') ||
                        t('common.system');

  let cardStatusClass = "card-success";

  const risk = proposal.risk_level.toLowerCase();
  if (risk === 'critical' || risk === 'high') {
    cardStatusClass = "card-critical card-pulse-critical";
  } else if (risk === 'medium' || risk === 'warning') {
    cardStatusClass = "card-warning";
  }

  return (
    <div
      className={`card card-proposal flex flex-col justify-between group relative ${cardStatusClass} ${isExpanded ? '!h-auto' : ''} ${removing ? 'opacity-0 scale-95 -translate-x-4 transition-all duration-500 ease-in-out pointer-events-none' : 'transition-all duration-300'}`}
    >
      <div className="flex items-start justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2 flex-wrap shrink-0">
          <span className={`text-[10px] font-extrabold font-interface tracking-wide uppercase px-1.5 py-0.5 rounded border whitespace-nowrap shrink-0 ${getRiskStyles(proposal.risk_level)}`}>
            {getRiskLabel(proposal.risk_level)}
          </span>
        </div>
      </div>

      <div className="my-3 min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-xs font-bold text-text-3 font-interface uppercase tracking-wider mb-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-accent" />
          <span>{t('prop.on_node', { node: nodeName })}</span>
        </div>
        <h5 className="text-xs font-mono text-text-1 font-bold truncate" title={displayTarget}>
          {t('prop.target')} : <span className="text-accent">{displayTarget}</span>
        </h5>
        <p className="text-text-2 text-sm font-sans mt-1.5 leading-relaxed" title={proposal.reasoning}>
          {isExpanded ? proposal.reasoning : (proposal.reasoning.length > 70 ? `${proposal.reasoning.substring(0, 70)}...` : proposal.reasoning)}
          {proposal.reasoning.length > 70 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1.5 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[11px]"
            >
              {isExpanded ? t('common.less') : t('common.more')}
            </button>
          )}
        </p>
      </div>

      <div className="flex flex-wrap gap-2 pt-3 border-t border-border/40 shrink-0 justify-between items-center w-full">
        {proposal.status !== 'PENDING' ? (
          <div className="w-full select-none">
            {proposal.status === 'APPROVED' || proposal.status === 'EXECUTED' ? (
              <div className="w-full px-3 py-1.5 rounded-lg bg-gradient-to-r from-severity-ok/15 to-severity-ok/5 border border-severity-ok/25 text-severity-ok flex items-center justify-between gap-2 shadow-[0_0_12px_rgba(34,197,94,0.15)]">
                <div className="flex items-center gap-1.5 font-bold font-interface text-xs uppercase tracking-wide">
                  <span className="relative flex h-2 w-2 shrink-0">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-severity-ok opacity-75 animate-ping"></span>
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-severity-ok"></span>
                  </span>
                  <Check className="w-3.5 h-3.5 shrink-0" />
                  <span>{t('prop.status_executed')}</span>
                </div>
                <span className="text-[10px] font-mono text-severity-ok/70 whitespace-nowrap">
                  {formatDateTime(proposal.executed_at || proposal.updated_at)}
                </span>
              </div>
            ) : proposal.status === 'FAILED' ? (
              <div className="w-full px-3 py-1.5 rounded-lg bg-gradient-to-r from-severity-critical/15 to-severity-critical/5 border border-severity-critical/25 text-severity-critical flex items-center justify-between gap-2 shadow-[0_0_12px_rgba(239,68,68,0.15)]">
                <div className="flex items-center gap-1.5 font-bold font-interface text-xs uppercase tracking-wide">
                  <span className="relative flex h-2 w-2 shrink-0">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-severity-critical opacity-75 animate-ping"></span>
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-severity-critical"></span>
                  </span>
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span>{t('prop.status_failed')}</span>
                </div>
                <span className="text-[10px] font-mono text-severity-critical/70 whitespace-nowrap">
                  {formatDateTime(proposal.executed_at || proposal.updated_at)}
                </span>
              </div>
            ) : (
              <div className="w-full px-3 py-1.5 rounded-lg bg-gradient-to-r from-surface-3/50 to-surface-3/25 border border-border text-text-3 flex items-center justify-between gap-2 hover:border-border-strong transition-all duration-200">
                <div className="flex items-center gap-1.5 font-bold font-interface text-xs uppercase tracking-wide">
                  <span className="relative flex h-2 w-2 shrink-0">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-text-3 opacity-50"></span>
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-text-3"></span>
                  </span>
                  <X className="w-3.5 h-3.5 shrink-0" />
                  <span>{t('prop.status_rejected')}</span>
                </div>
                <span className="text-[10px] font-mono text-text-3/70 whitespace-nowrap">
                  {formatDateTime(proposal.updated_at)}
                </span>
              </div>
            )}
          </div>
        ) : isOperator ? (
          <>
            <button
              onClick={() => onReject(proposal.id)}
              disabled={loading}
              className="flex-1 min-w-[110px] flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-bold font-interface tracking-wide uppercase border border-severity-critical/20 hover:border-severity-critical/50 hover:bg-severity-critical/10 text-severity-critical/80 hover:text-severity-critical rounded cursor-pointer disabled:opacity-50 transition-all duration-150"
            >
              <X className="w-3 h-3 shrink-0" />
              <span>{t('prop.btn.reject')}</span>
            </button>
            <button
              onClick={() => onApprove(proposal.id)}
              disabled={loading}
              className="flex-1 min-w-[110px] flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-bold font-interface tracking-wide uppercase bg-accent hover:bg-accent-hover text-text-1 rounded shadow-md shadow-accent/15 cursor-pointer disabled:opacity-50 transition-all duration-150"
            >
              <Check className="w-3 h-3 shrink-0" />
              <span>{t('prop.btn.approve')}</span>
            </button>
          </>
        ) : (
          <div className="flex-1 flex items-center gap-1.5 text-text-3 text-xs italic py-1 bg-surface-2 justify-center rounded">
            <AlertTriangle className="w-3 h-3 text-text-3" />
            <span>{t('prop.readonly')}</span>
          </div>
        )}
      </div>
    </div>
  );
};
