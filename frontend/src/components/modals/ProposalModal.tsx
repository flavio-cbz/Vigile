import React, { useState } from 'react';
import { useLocale } from '../../i18n';
import { X, Terminal } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useNodeStore } from '../../store/nodeStore';
import { useToastStore } from '../../store/useToastStore';

interface Proposal {
  id: string;
  node_id: string;
  action: string;
  params_json: string;
  reasoning: string;
  risk_level: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'FAILED' | 'EXECUTED';
  created_by: string;
  approved_by: string | null;
  rejected_by: string | null;
  rejection_reason: string | null;
  created_at: number;
  updated_at: number;
  executed_at: number | null;
  result_json: string | null;
}

interface ProposalModalProps {
  proposal: Proposal;
  onClose: () => void;
  onProposalUpdated: (proposalId: string, newStatus: string) => void;
}

export const ProposalModal: React.FC<ProposalModalProps> = ({
  proposal,
  onClose,
  onProposalUpdated,
}) => {
  const { t } = useLocale();
  const accessToken = useAuthStore((s) => s.accessToken);
  const nodes = useNodeStore((s) => s.nodes);
  const addToast = useToastStore((s) => s.addToast);

  const [rejectionReason, setRejectionReason] = useState('');
  const [isRejectingState, setIsRejectingState] = useState(false);

  const getNodeName = (nodeId: string) => {
    const node = nodes.find(n => n.id === nodeId);
    return node ? node.name : t('proposal_modal.node_short', { id: nodeId.substring(0, 8) });
  };

  const formatEpoch = (epoch: number) => {
    return new Date(epoch * 1000).toLocaleString('fr-FR');
  };

  const handleApproveProposal = async (proposalId: string) => {
    try {
      const res = await fetch(`/api/chat/proposals/${proposalId}/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });
      if (res.ok) {
        addToast('success', t('proposal_modal.toast_approved'), '');
        onProposalUpdated(proposalId, 'APPROVED');
        onClose();
      } else {
        const data = await res.json();
        addToast('error', t('settings.error'), data.detail || t('proposal_modal.toast_error'));
      }
    } catch (e) {
      console.error(e);
      addToast('error', t('settings.error'), t('chat.error_communication'));
    }
  };

  const handleRejectProposal = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`/api/chat/proposals/${proposal.id}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`
        },
        body: JSON.stringify({ reason: rejectionReason || t('proposal_modal.rejected_by_operator') })
      });
      if (res.ok) {
        addToast('success', t('proposal_modal.toast_rejected'), '');
        onProposalUpdated(proposal.id, 'REJECTED');
        onClose();
      } else {
        const data = await res.json();
        addToast('error', t('settings.error'), data.detail || t('proposal_modal.toast_error'));
      }
    } catch (e) {
      console.error(e);
      addToast('error', t('settings.error'), t('chat.error_communication'));
    }
  };

  const handleClose = () => {
    setIsRejectingState(false);
    setRejectionReason('');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-bg/85 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-in">
      <div className="w-full max-w-2xl glass-panel p-6 rounded-xl border border-border-custom shadow-2xl space-y-4 animate-fade-up relative">
        <button
          onClick={handleClose}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink cursor-pointer p-1 rounded hover:bg-surface-hover"
        >
          <X className="w-4 h-4" />
        </button>

        <div>
          <div className="flex items-center gap-2">
            <span className={`text-[0.5625rem] font-bold px-2 py-0.5 rounded border uppercase tracking-wider font-mono ${
              proposal.risk_level === 'HIGH' ? 'border-red-border bg-red-soft/20 text-red-custom' :
              proposal.risk_level === 'MEDIUM' ? 'border-amber-border bg-amber-soft/20 text-amber-custom' :
              'border-green-border bg-green-soft/20 text-green-custom'
            }`}>
              {t('prop.risk')}: {proposal.risk_level}
            </span>
            <span className="text-xs font-bold text-ink-muted">
              {t('proposal_modal.associated_node')} {getNodeName(proposal.node_id)}
            </span>
          </div>
          <h3 className="text-sm font-bold text-ink uppercase tracking-wider flex items-center gap-2 mt-2">
            <Terminal className="w-4 h-4 text-accent-custom" />
            <span>{t('proposal_modal.title')}</span>
          </h3>
        </div>

        <div className="space-y-3">
          <div className="space-y-1">
            <span className="text-[0.5625rem] font-bold text-ink-muted uppercase tracking-wider">{t('proposal_modal.action_label')}</span>
            <div className="p-3 rounded-lg bg-bg border border-border-strong font-mono text-[0.625rem] text-ink overflow-x-auto whitespace-pre-wrap shadow-inner max-h-48">
              {proposal.action}
            </div>
          </div>

          {proposal.reasoning && (
            <div className="space-y-1">
              <span className="text-[0.5625rem] font-bold text-ink-muted uppercase tracking-wider">{t('proposal_modal.justification')}</span>
              <p className="text-[0.6875rem] text-ink-dim leading-relaxed bg-surface/30 p-2.5 rounded border border-border-custom/50">
                {proposal.reasoning}
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 text-[0.625rem] border-t border-b border-border-custom/40 py-2.5">
            <div>
              <span className="text-ink-muted font-bold block uppercase tracking-wider text-[0.5rem] mb-0.5">{t('proposal_modal.created_by')}</span>
              <span className="font-semibold text-ink">{proposal.created_by}</span>
            </div>
            <div>
              <span className="text-ink-muted font-bold block uppercase tracking-wider text-[0.5rem] mb-0.5">{t('proposal_modal.created_at')}</span>
              <span className="font-semibold text-ink">{formatEpoch(proposal.created_at)}</span>
            </div>
            <div>
              <span className="text-ink-muted font-bold block uppercase tracking-wider text-[0.5rem] mb-0.5">{t('proposal_modal.current_status')}</span>
              <span className="font-semibold text-ink uppercase">{proposal.status}</span>
            </div>
            {proposal.executed_at && (
              <div>
                <span className="text-ink-muted font-bold block uppercase tracking-wider text-[0.5rem] mb-0.5">{t('proposal_modal.executed_at')}</span>
                <span className="font-semibold text-ink">{formatEpoch(proposal.executed_at)}</span>
              </div>
            )}
          </div>

          {proposal.rejection_reason && (
            <div className="p-2.5 bg-red-soft/10 border border-red-border/30 rounded-lg text-[0.625rem] text-red-custom">
              <span className="font-bold block uppercase tracking-wider text-[0.5rem] mb-1">{t('proposal_modal.rejection_reason')}</span>
              {proposal.rejection_reason}
            </div>
          )}

          {proposal.result_json && (
            <div className="space-y-1">
              <span className="text-[0.5625rem] font-bold text-ink-muted uppercase tracking-wider">{t('proposal_modal.execution_result')}</span>
              <pre className="p-3 rounded-lg bg-bg border border-border-strong font-mono text-[0.5625rem] text-ink overflow-x-auto whitespace-pre shadow-inner max-h-36">
                {proposal.result_json}
              </pre>
            </div>
          )}
        </div>

        <div className="flex justify-between items-center pt-3 border-t border-border-custom/50">
          <div className="text-[0.5625rem] font-mono text-ink-muted">
            {t('proposal_modal.uuid', { id: proposal.id })}
          </div>

          <div className="flex gap-2">
            {proposal.status === 'PENDING' ? (
              isRejectingState ? (
                <form onSubmit={handleRejectProposal} className="flex gap-2 w-full">
                  <input
                    type="text"
                    required
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    placeholder={t('proposal_modal.rejection_placeholder')}
                    className="bg-bg border border-red-border text-xs rounded px-2.5 py-1.5 text-ink w-60 focus:outline-hidden"
                  />
                  <button
                    type="submit"
                    className="px-3.5 py-1.5 rounded-lg bg-red-custom text-bg text-[0.625rem] font-bold hover:bg-red-custom/90 cursor-pointer"
                  >
                    {t('proposal_modal.validate_reject')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsRejectingState(false)}
                    className="px-3.5 py-1.5 rounded-lg border border-border-strong text-ink text-[0.625rem] font-bold cursor-pointer"
                  >
                    {t('modal.cancel')}
                  </button>
                </form>
              ) : (
                <>
                  <button
                    onClick={() => setIsRejectingState(true)}
                    className="px-4 py-2 rounded-lg border border-red-border hover:bg-red-soft/20 text-red-custom text-[0.6875rem] font-bold cursor-pointer transition-colors"
                  >
                    {t('proposal_modal.reject')}
                  </button>
                  <button
                    onClick={() => handleApproveProposal(proposal.id)}
                    className="px-4 py-2 rounded-lg bg-accent-soft border border-accent-border text-accent-custom hover:bg-accent-custom hover:text-bg text-[0.6875rem] font-bold cursor-pointer transition-all duration-150 shadow-sm"
                  >
                    {t('proposal_modal.approve_execute')}
                  </button>
                </>
              )
            ) : (
              <button
                onClick={handleClose}
                className="px-4 py-2 rounded-lg border border-border-strong text-ink text-[0.6875rem] font-bold cursor-pointer hover:bg-surface-hover"
              >
                {t('proposal_modal.close')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
