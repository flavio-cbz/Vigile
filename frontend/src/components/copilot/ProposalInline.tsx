import React from 'react';
import { Check, X, ShieldAlert, ChevronDown } from 'lucide-react';
import { useLocale } from '../../i18n';
import { usePermission } from '../../hooks/usePermission';
import { CopyableId } from '../ui/CopyableId';

interface ProposalInlineProps {
  proposalId: string;
  action: string;
  target?: string;
  riskLevel: string;
  reasoning?: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED';
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
  loading?: boolean;
  /** Optional ref callback to attach the highlight flash ring when navigated to. */
  registerRef?: (el: HTMLDivElement | null) => void;
}

const normalizeRisk = (risk: string): 'low' | 'medium' | 'high' | 'critical' => {
  const r = risk.toLowerCase();
  if (r === 'critical' || r === 'critique') return 'critical';
  if (r === 'high') return 'high';
  if (r === 'medium' || r === 'warning') return 'medium';
  return 'low';
};

export const ProposalInline: React.FC<ProposalInlineProps> = ({
  proposalId,
  action,
  target,
  riskLevel,
  reasoning,
  status,
  onApprove,
  onReject,
  loading = false,
  registerRef,
}) => {
  const { t } = useLocale();
  const { can } = usePermission();
  const isOperator = can('approve-action');
  const risk = normalizeRisk(riskLevel);
  const reasoningLong = (reasoning?.length ?? 0) > 200;

  const getRiskLabel = () => {
    switch (risk) {
      case 'critical': return t('prop.risk_critical');
      case 'high': return t('prop.risk_high');
      case 'medium': return t('prop.risk_medium');
      case 'low': return t('prop.risk_low');
      default: return riskLevel.toUpperCase();
    }
  };

  const renderStatusFooter = () => {
    switch (status) {
      case 'APPROVED':
      case 'EXECUTED':
        return (
          <div className="w-full text-center py-2 bg-severity-ok/10 text-severity-ok border border-severity-ok/25 rounded-md font-bold text-[11px] uppercase tracking-wider">
            {t('prop.status_executed')}
          </div>
        );
      case 'REJECTED':
        return (
          <div className="w-full text-center py-2 bg-text-3/10 text-text-2 border border-border rounded-md font-bold text-[11px] uppercase tracking-wider">
            {t('prop.status_rejected')}
          </div>
        );
      case 'FAILED':
        return (
          <div className="w-full text-center py-2 bg-severity-critical/15 text-severity-critical border border-severity-critical/25 rounded-md font-bold text-[11px] uppercase tracking-wider animate-pulse">
            {t('prop.status_failed')}
          </div>
        );
      case 'PENDING':
      default:
        if (!isOperator) {
          return (
            <div className="w-full text-center py-2 text-text-3 italic font-sans text-[11px]">
              {t('prop.readonly')}
            </div>
          );
        }
        return (
          <div className="flex gap-2 w-full">
            <button
              onClick={() => onReject(proposalId)}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-1 py-2 text-[11px] font-bold border border-border hover:border-severity-critical/30 hover:bg-severity-critical/5 text-text-2 hover:text-severity-critical rounded-md cursor-pointer transition-all duration-150 disabled:opacity-50"
            >
              <X className="w-3 h-3" />
              <span>{t('prop.btn.reject')}</span>
            </button>
            <button
              onClick={() => onApprove(proposalId)}
              disabled={loading}
              className="cp-smart-action-approve-btn flex-1 flex items-center justify-center gap-1 py-2 text-[11px] rounded-md cursor-pointer transition-all duration-150 disabled:opacity-50"
            >
              <Check className="w-3 h-3" />
              <span>{t('prop.btn.approve')}</span>
            </button>
          </div>
        );
    }
  };

  return (
    <div
      ref={(el) => {
        if (registerRef) registerRef(el);
      }}
      className={`cp-smart-action animate-fade-in ${status === 'PENDING' ? 'cp-highlight-ring' : ''}`}
      data-risk={risk}
    >
      <div className="flex items-center justify-between gap-2 border-b border-glass-border pb-2.5">
        <span className="text-[10px] font-extrabold tracking-widest text-accent-info-strong uppercase font-interface flex items-center gap-1.5">
          <ShieldAlert className="w-3.5 h-3.5" />
          {t('prop.title')}
        </span>
        <span className="text-[10px] font-extrabold tracking-widest uppercase px-2 py-0.5 border rounded-full bg-surface/40">
          {t('prop.risk')} {getRiskLabel()}
        </span>
      </div>

      <div className="space-y-1.5 pt-2">
        <p className="font-mono text-base text-text-1 font-bold tracking-tight">
          {t('prop.action')} : <span className="text-accent">{action}</span>
        </p>
        {target && (
          <p className="font-mono text-[11px] text-text-2 flex items-center gap-2 flex-wrap">
            {t('prop.target')} :
            <CopyableId value={target} />
          </p>
        )}
        {reasoning && (
          <details className="pt-2 group" open={!reasoningLong}>
            <summary className="cursor-pointer text-text-3 text-[10px] uppercase tracking-wider flex items-center gap-1 select-none hover:text-text-2 transition-colors">
              <ChevronDown className="w-3 h-3 transition-transform group-open:rotate-0 rotate-[-90deg]" />
              {t('copilot.proposal_reasoning')}
            </summary>
            <p className="text-text-2 text-[11.5px] leading-relaxed pt-1.5 font-normal">
              {reasoning}
            </p>
          </details>
        )}
      </div>

      <div className="pt-3 border-t border-glass-border shrink-0">
        {renderStatusFooter()}
      </div>
    </div>
  );
};
