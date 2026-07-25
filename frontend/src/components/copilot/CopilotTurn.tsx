import React from 'react';
import type { Message } from '../../store/chatStore';
import { CopilotMessage } from './CopilotMessage';

interface CopilotTurnProps {
  messages: Message[];
  onApproveProposal: (id: string) => Promise<void>;
  onRejectProposal: (id: string) => Promise<void>;
  loadingProposalId?: string | null;
  /** Ref map callback: store proposalId -> element for highlight-on-ticker. */
  registerProposalRef?: (proposalId: string, el: HTMLDivElement | null) => void;
}

/**
 * A "turn" is a user message followed by everything between it and the next
 * user message (assistant replies, tool execution summaries, embedded proposals).
 *
 * Grouping renders the conversation as a cardified vertical flow instead of flat
 * log rows, improving causal readability over long ReAct loops.
 */
export const CopilotTurn: React.FC<CopilotTurnProps> = ({
  messages,
  onApproveProposal,
  onRejectProposal,
  loadingProposalId,
  registerProposalRef,
}) => {
  return (
    <section className="cp-turn">
      {messages.map((msg, idx) => (
        <CopilotMessage
          key={`${msg.role}-${idx}`}
          message={msg}
          onApproveProposal={onApproveProposal}
          onRejectProposal={onRejectProposal}
          loadingProposal={loadingProposalId === msg.proposal?.id}
          registerProposalRef={
            msg.proposal
              ? (el) => registerProposalRef?.(msg.proposal!.id, el)
              : undefined
          }
        />
      ))}
    </section>
  );
};
