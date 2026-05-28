import React from 'react';
import { Terminal, CheckCircle2, AlertCircle, Clock } from 'lucide-react';
import { useLocale } from '../../i18n';

interface Proposal {
  id: string;
  node_id: string;
  action: string;
  risk_level: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'FAILED' | 'EXECUTED';
  created_at: number;
}

interface ActivityCardProps {
  proposal: Proposal;
  nodeName: string;
  onClick: () => void;
}

export const ActivityCard: React.FC<ActivityCardProps> = ({
  proposal,
  nodeName,
  onClick,
}) => {
  const { t } = useLocale();

  const getStatusStyle = () => {
    switch (proposal.status) {
      case 'PENDING':
        return {
          border: 'border-warning/20 hover:border-warning/45',
          badge: 'badge-warning',
          icon: <Clock size={12} className="text-warning" />
        };
      case 'APPROVED':
      case 'EXECUTED':
        return {
          border: 'border-success/20 hover:border-success/45',
          badge: 'badge-success',
          icon: <CheckCircle2 size={12} className="text-success" />
        };
      default:
        return {
          border: 'border-danger/20 hover:border-danger/45',
          badge: 'badge-danger',
          icon: <AlertCircle size={12} className="text-danger" />
        };
    }
  };

  const statusStyle = getStatusStyle();

  return (
    <div
      onClick={onClick}
      className={`w-[270px] h-[135px] bg-surface-0 border ${statusStyle.border} rounded-xl p-4 flex flex-col justify-between hover:bg-surface-1 cursor-pointer transition-all duration-200 shadow-sm animate-fade-in`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/40 pb-2">
        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider font-mono ${
          proposal.risk_level === 'HIGH' ? 'border-danger/30 bg-danger-subtle text-danger' :
          proposal.risk_level === 'MEDIUM' ? 'border-warning/30 bg-warning-subtle text-warning' :
          'border-success/30 bg-success-subtle text-success'
        }`}>
          {proposal.risk_level}
        </span>
        <span className="text-[10px] font-bold text-ink-muted truncate max-w-[130px]" title={nodeName}>
          {nodeName}
        </span>
      </div>

      {/* Action preview */}
      <div className="my-2 p-2 rounded bg-surface-2 border border-border font-mono text-[10px] text-ink-secondary truncate shadow-inner flex items-center gap-1.5">
        <Terminal size={10} className="text-accent-primary shrink-0" />
        <span className="truncate">{proposal.action}</span>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-ink-muted font-mono">
        <span>
          {new Date(proposal.created_at * 1000).toLocaleDateString('fr-FR', {
            day: '2-digit',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
          })}
        </span>
        <span className={`badge ${statusStyle.badge} flex items-center gap-1`}>
          {statusStyle.icon}
          {t(`prop.status.${proposal.status.toLowerCase()}` as any)}
        </span>
      </div>
    </div>
  );
};
