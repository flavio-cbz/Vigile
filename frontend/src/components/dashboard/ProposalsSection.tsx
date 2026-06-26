import React from 'react';
import { CheckSquare } from 'lucide-react';
import { useLocale } from '../../i18n';
import { SwimLane } from './SwimLane';
import { ProposalCard } from './ProposalCard';
import { ProposalRejectModal } from './ProposalRejectModal';
import type { ActionProposal } from '../../store/uiStore';
import type { Node } from '../../store/nodeStore';

interface ProposalsSectionProps {
  proposals: ActionProposal[];
  nodes: Node[];
  loadingProposalId: string | null;
  rejectingProposalId: string | null;
  rejectReason: string;
  onApprove: (id: string) => Promise<void>;
  onRejectInit: (id: string) => void;
  onRejectCancel: () => void;
  onRejectChange: (reason: string) => void;
  onRejectConfirm: (id: string, reason: string) => Promise<void>;
}

export const ProposalsSection: React.FC<ProposalsSectionProps> = ({
  proposals,
  nodes,
  loadingProposalId,
  rejectingProposalId,
  rejectReason,
  onApprove,
  onRejectInit,
  onRejectCancel,
  onRejectChange,
  onRejectConfirm,
}) => {
  const { t } = useLocale();

  if (proposals.length === 0) return null;

  return (
    <>
      <SwimLane
        title={t('dash.proposed_actions')}
        icon={CheckSquare}
        className="border-t border-border/30 pt-6 mt-6"
        layout="grid"
      >
        {proposals.map((prop) => {
          const node = nodes.find((n) => n.id === prop.node_id);
          return (
            <ProposalCard
              key={prop.id}
              proposal={prop}
              nodeName={node ? node.name : t('common.system')}
              onApprove={onApprove}
              onReject={async (id) => {
                onRejectInit(id);
              }}
              loading={loadingProposalId === prop.id}
            />
          );
        })}
      </SwimLane>

      {rejectingProposalId && (
        <ProposalRejectModal
          reason={rejectReason}
          onChange={onRejectChange}
          onCancel={onRejectCancel}
          onConfirm={() => onRejectConfirm(rejectingProposalId, rejectReason)}
        />
      )}
    </>
  );
};
