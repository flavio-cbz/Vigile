import React from 'react';
import type { Message } from '../../store/chatStore';
import { ProposalInline } from './ProposalInline';
import { Sparkles, User, Terminal } from 'lucide-react';

interface CopilotMessageProps {
  message: Message;
  onApproveProposal: (id: string) => Promise<void>;
  onRejectProposal: (id: string) => Promise<void>;
  loadingProposal?: boolean;
}

export const CopilotMessage: React.FC<CopilotMessageProps> = ({
  message,
  onApproveProposal,
  onRejectProposal,
  loadingProposal = false,
}) => {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) {
    return (
      <div className="flex items-start gap-2 px-4 py-2 bg-surface-2/45 border-y border-border/40 font-mono text-[9px] text-text-3 leading-normal">
        <Terminal className="w-3.5 h-3.5 text-text-3 shrink-0 mt-0.5" />
        <span className="break-all">{message.content}</span>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 px-4 py-3 border-b border-border/30 ${
      isUser ? 'bg-surface/30' : 'bg-surface-2/30'
    }`}>
      <div className="shrink-0 mt-0.5">
        {isUser ? (
          <div className="w-6.5 h-6.5 rounded-full bg-surface-3 border border-border flex items-center justify-center text-text-2">
            <User className="w-3.5 h-3.5" />
          </div>
        ) : (
          <div className="w-6.5 h-6.5 rounded-full bg-accent/15 border border-accent/25 flex items-center justify-center shadow-inner">
            <Sparkles className="w-3.5 h-3.5 text-accent" />
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0 space-y-3 font-sans text-xs">
        <div className="flex items-center gap-1.5 justify-between">
          <span className="font-bold text-[10px] tracking-wide text-text-1 font-interface">
            {isUser ? 'VOUS' : 'COPILOTE IA'}
          </span>
        </div>

        <p className="text-text-2 leading-relaxed whitespace-pre-wrap break-words">
          {message.content || (
            <span className="inline-flex gap-1 items-center opacity-60">
              <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          )}
        </p>

        {message.proposal && (
          <div className="mt-2 animate-fade-in">
            <ProposalInline
              proposalId={message.proposal.id}
              action={message.proposal.action}
              target={message.proposal.target || message.proposal.params?.target}
              riskLevel={message.proposal.risk_level}
              reasoning={message.proposal.reasoning}
              status={message.proposal.status || 'PENDING'}
              onApprove={onApproveProposal}
              onReject={onRejectProposal}
              loading={loadingProposal}
            />
          </div>
        )}
      </div>
    </div>
  );
};
