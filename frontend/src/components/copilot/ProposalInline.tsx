import React from 'react';
import { Check, X, ShieldAlert } from 'lucide-react';
import { useLocale } from '../../i18n';
import { usePermission } from '../../hooks/usePermission';

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
}

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
}) => {
  const { t } = useLocale();
  const { can } = usePermission();
  const isOperator = can('approve-action');

  const getRiskStyles = () => {
    switch (riskLevel.toLowerCase()) {
      case 'high':
      case 'critique':
        return 'text-severity-critical border-severity-critical/20 bg-severity-critical/5';
      case 'medium':
      case 'warning':
        return 'text-severity-warning border-severity-warning/20 bg-severity-warning/5';
      case 'low':
      case 'ok':
      default:
        return 'text-severity-ok border-severity-ok/20 bg-severity-ok/5';
    }
  };

  const getRiskLabel = () => {
    switch (riskLevel.toLowerCase()) {
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
          <div className="w-full text-center py-1.5 bg-severity-ok/10 text-severity-ok border border-severity-ok/20 rounded font-bold text-[9px] uppercase tracking-wider">
            {t('prop.status_executed')}
          </div>
        );
      case 'REJECTED':
        return (
          <div className="w-full text-center py-1.5 bg-text-3/15 text-text-2 border border-border rounded font-bold text-[9px] uppercase tracking-wider">
            {t('prop.status_rejected')}
          </div>
        );
      case 'FAILED':
        return (
          <div className="w-full text-center py-1.5 bg-severity-critical/15 text-severity-critical border border-severity-critical/20 rounded font-bold text-[9px] uppercase tracking-wider animate-pulse">
            {t('prop.status_failed')}
          </div>
        );
      case 'PENDING':
      default:
        if (!isOperator) {
          return (
            <div className="w-full text-center py-1 text-text-3 italic font-sans text-[9px]">
              {t('prop.readonly')}
            </div>
          );
        }
        return (
          <div className="flex gap-2 w-full">
            <button
              onClick={() => onReject(proposalId)}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-0.5 py-1.5 text-[9px] font-bold border border-border hover:border-severity-critical/30 hover:bg-severity-critical/5 text-text-2 hover:text-severity-critical rounded cursor-pointer transition-all duration-150"
            >
              <X className="w-2.5 h-2.5" />
              <span>{t('prop.btn.reject')}</span>
            </button>
            <button
              onClick={() => onApprove(proposalId)}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-0.5 py-1.5 text-[9px] font-bold bg-accent hover:bg-accent-hover text-text-1 rounded cursor-pointer transition-all duration-150"
            >
              <Check className="w-2.5 h-2.5" />
              <span>{t('prop.btn.approve')}</span>
            </button>
          </div>
        );
    }
  };

  return (
    <div className="w-full bg-surface border border-border rounded-lg p-3.5 space-y-3 font-sans text-xs shadow-inner">
      <div className="flex items-center justify-between gap-2 border-b border-border/40 pb-2">
        <span className="text-[8px] font-extrabold tracking-widest text-accent uppercase font-interface flex items-center gap-1">
          <ShieldAlert className="w-3 h-3 text-accent animate-pulse" /> {t('prop.title')}
        </span>
        <span className={`text-[8px] font-extrabold tracking-widest uppercase px-1.5 py-0.5 border rounded ${getRiskStyles()}`}>
          {t('prop.risk')} {getRiskLabel()}
        </span>
      </div>

      <div className="space-y-1">
        <p className="font-mono text-[10px] text-text-1 font-bold">
          {t('prop.action')} : <span className="text-accent">{action}</span>
        </p>
        {target && (
          <p className="font-mono text-[10px] text-text-2">
            {t('prop.target')} : <code className="text-text-1 font-bold">{target}</code>
          </p>
        )}
        {reasoning && (
          <p className="text-text-2 text-[10.5px] leading-relaxed pt-1 font-normal">
            {reasoning}
          </p>
        )}
      </div>

      <div className="pt-2 border-t border-border/20 shrink-0">
        {renderStatusFooter()}
      </div>
    </div>
  );
};
