import React, { useMemo, useState } from 'react';
import { CheckSquare } from 'lucide-react';
import { useNavigate } from 'react-router';
import { useLocale } from '../../i18n';
import { SwimLane } from './SwimLane';
import { ProposalCard } from './ProposalCard';
import { ProposalRejectModal } from './ProposalRejectModal';
import type { ActionProposal } from '../../store/uiStore';
import type { Node } from '../../store/nodeStore';
import { sortProposalsByRiskAndDate } from '../../utils/proposalSort';

export const PROPOSALS_DASHBOARD_LIMIT = 5;

interface ProposalsSectionProps {
  proposals: ActionProposal[];
  nodes: Node[];
  loadingProposalId: string | null;
  rejectingProposalId: string | null;
  rejectReason: string;
  removingProposalId: string | null;
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
  removingProposalId,
  onApprove,
  onRejectInit,
  onRejectCancel,
  onRejectChange,
  onRejectConfirm,
}) => {
  const { t } = useLocale();
  const navigate = useNavigate();
  const sorted = useMemo(() => sortProposalsByRiskAndDate(proposals), [proposals]);
  const [visibleCount, setVisibleCount] = useState(PROPOSALS_DASHBOARD_LIMIT);
  const visible = sorted.slice(0, visibleCount);
  const remaining = sorted.length - visible.length;
  const nextChunk = Math.min(PROPOSALS_DASHBOARD_LIMIT, remaining);
  const handleSeeMore = () => {
    setVisibleCount((c) => Math.min(c + PROPOSALS_DASHBOARD_LIMIT, sorted.length));
  };

  if (proposals.length === 0) return null;

  return (
    <>
      <SwimLane
        title={t('dash.proposed_actions')}
        icon={CheckSquare}
        className="border-t border-border/30 pt-6 mt-6"
        layout="grid"
        onSeeAll={sorted.length > PROPOSALS_DASHBOARD_LIMIT ? () => navigate('/proposals') : undefined}
      >
        {visible.map((prop) => {
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
              removing={removingProposalId === prop.id}
            />
          );
        })}
      </SwimLane>
      {remaining > 0 && (
        <div className="flex justify-center pt-2">
          <button
            onClick={handleSeeMore}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg border border-border bg-surface-2 hover:bg-surface-hover text-text-1 font-mono text-xs font-semibold uppercase tracking-wider transition-colors duration-150 cursor-pointer"
          >
            {t('proposals.see_more_chunk', { count: nextChunk })}
          </button>
        </div>
      )}

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
