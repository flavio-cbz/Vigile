import React from 'react';
import type { Message } from '../../store/chatStore';
import { ProposalInline } from './ProposalInline';
import { CopilotToolLine } from './CopilotToolLine';
import { useLocale } from '../../i18n';
import { Sparkles, User, Copy } from 'lucide-react';

interface CopilotMessageProps {
  message: Message;
  onApproveProposal: (id: string) => Promise<void>;
  onRejectProposal: (id: string) => Promise<void>;
  loadingProposal?: boolean;
  /** Ref callback used to attach highlight ring when navigated from pending ticker. */
  registerProposalRef?: (el: HTMLDivElement | null) => void;
}

export const CopilotMessage: React.FC<CopilotMessageProps> = ({
  message,
  onApproveProposal,
  onRejectProposal,
  loadingProposal = false,
  registerProposalRef,
}) => {
  const { t } = useLocale();
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isTool = message.role === 'tool';

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content).catch(() => {
      // Silent clipboard fallback in non-secure contexts.
    });
  };

  if (isSystem) {
    return (
      <div className="px-3 py-1.5 my-1 bg-surface-3/30 border border-border/40 rounded-md font-mono text-[10px] text-text-3 leading-normal break-all">
        {message.content}
      </div>
    );
  }

  if (isTool) {
    return (
      <div className="flex items-center gap-2 px-3 py-1 my-0.5 bg-accent-info-soft/40 border-l-2 border-accent-info/50 text-[10px] text-text-3 leading-relaxed font-mono rounded-r-md">
        <span>Outil :</span>
        <code className="text-text-1 font-bold">{message.name || 'tool'}</code>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="flex gap-3 px-2 py-1.5">
        <div className="shrink-0 mt-0.5">
          <div className="w-7 h-7 rounded-full bg-surface-3 border border-border flex items-center justify-center text-text-2">
            <User className="w-3.5 h-3.5" />
          </div>
        </div>
        <div className="flex-1 min-w-0 space-y-1.5">
          <span className="font-bold text-[9.5px] tracking-wider text-text-3 uppercase font-interface">
            {t('copilot.user_badge')}
          </span>
          <div className="cp-bubble-user font-sans text-[12.5px] whitespace-pre-wrap break-words">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  // Assistant message
  const isStreaming = !message.content;
  const hasTools = (message.tools?.length ?? 0) > 0;

  return (
    <div className="flex gap-3 px-2 py-1.5">
      <div className="shrink-0 mt-0.5">
        <div className="w-7 h-7 rounded-full bg-accent-info/15 border border-accent-info/30 flex items-center justify-center shadow-inner">
          <Sparkles className="w-3.5 h-3.5 text-accent-info-strong" />
        </div>
      </div>

      <div className="flex-1 min-w-0 space-y-2.5 font-sans">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-bold text-[9.5px] tracking-wider text-accent-info-strong uppercase font-interface">
            {t('copilot.copilot_badge')}
          </span>
          {message.model && (
            <span className="font-mono text-[9.5px] text-text-3 bg-surface-3/40 border border-border rounded px-1.5 py-0.5">
              {message.model}
            </span>
          )}
          {message.latencyMs !== undefined && (
            <span className="font-mono text-[9.5px] text-text-3 tabular-nums">
              {message.latencyMs}ms
            </span>
          )}
          {message.content && (
            <button
              onClick={handleCopy}
              className="ml-auto text-text-3 hover:text-text-1 transition-colors p-1 rounded-md hover:bg-surface-3/40"
              title={t('copilot.copy_tooltip')}
              aria-label={t('copilot.copy_tooltip')}
            >
              <Copy className="w-3 h-3" />
            </button>
          )}
        </div>

        {isStreaming ? (
          <div className="cp-bubble-assistant text-text-2">
            <span className="cp-agent-typing text-accent-info-strong">
              <span />
              <span />
              <span />
            </span>
          </div>
        ) : (
          <div className="cp-bubble-assistant text-text-2 text-[12.5px] leading-relaxed">
            {message.content}
          </div>
        )}

        {hasTools && (
          <div className="space-y-1 py-1">
            {message.tools!.map((tool, idx) => (
              <CopilotToolLine key={idx} tool={tool} />
            ))}
          </div>
        )}

        {message.proposal && (
          <div className="pt-1.5">
            <ProposalInline
              proposalId={message.proposal.id}
              action={message.proposal.action}
              target={message.proposal.target || (typeof message.proposal.params?.target === 'string' ? message.proposal.params.target : undefined)}
              riskLevel={message.proposal.risk_level}
              reasoning={message.proposal.reasoning}
              status={message.proposal.status || 'PENDING'}
              onApprove={onApproveProposal}
              onReject={onRejectProposal}
              loading={loadingProposal}
              registerRef={registerProposalRef}
            />
          </div>
        )}
      </div>
    </div>
  );
};
