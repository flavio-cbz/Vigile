import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useUiStore } from '../../store/uiStore';
import { useChatStore } from '../../store/chatStore';
import { useNodeStore } from '../../store/nodeStore';
import { CopilotHeader } from './CopilotHeader';
import { CopilotSidebar } from './CopilotSidebar';
import { CopilotInput } from './CopilotInput';
import { CopilotTurn } from './CopilotTurn';
import { groupByTurns } from './chatUtils';
import { CopilotPendingTicker } from './CopilotPendingTicker';
import { useLocale } from '../../i18n';
import { Spinner } from '../primitives/Spinner';
import { MessageSquare, Zap, Terminal } from 'lucide-react';

export const CopilotPanel: React.FC = () => {
  const { t } = useLocale();
  const { copilotOpen, copilotContext, closeCopilot } = useUiStore();
  const { nodes } = useNodeStore();
  const {
    activeSession,
    isStreaming,
    activeSteps,
    activeTools,
    activeMeta,
    suggestions,
    sendMessage,
    createSession,
    fetchSessions,
    selectSession,
    fetchSuggestions,
    approveProposal,
    rejectProposal,
    abortStreaming,
    pendingProposalsCount,
  } = useChatStore();

  const [loadingSession, setLoadingSession] = useState(false);
  const [loadingProposalId, setLoadingProposalId] = useState<string | null>(null);
  const proposalRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());

  const nodeId = copilotContext?.node_id || null;
  const targetNode = nodes.find((n) => n.id === nodeId);

  // Click-outside & Escape-to-close behave as before.
  useEffect(() => {
    if (!copilotOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      // Ignore clicks within the panel itself or any element labeled data-copilot-anchor.
      if (target.closest('[data-copilot-root]') || target.closest('[data-copilot-anchor]')) return;
      closeCopilot();
    };
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [copilotOpen, closeCopilot]);

  useEffect(() => {
    if (!copilotOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeCopilot();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [copilotOpen, closeCopilot]);

  // Abort streaming & reset trigger state on panel close.
  useEffect(() => {
    if (!copilotOpen) {
      triggerProcessedRef.current = false;
      useChatStore.getState().abortStreaming();
    }
  }, [copilotOpen]);

  // Session bootstrap on open.
  useEffect(() => {
    if (!copilotOpen) return;

    const setupSession = async () => {
      setLoadingSession(true);
      try {
        await fetchSessions(nodeId);
        await fetchSuggestions(nodeId);

        const { sessions: latestSessions } = useChatStore.getState();
        const nodeSessions = latestSessions.filter((s) => s.node_id === nodeId);
        if (nodeSessions.length > 0) {
          selectSession(nodeSessions[0].id);
        } else {
          await createSession(nodeId, `Focus : ${targetNode?.name || t('copilot.scope_global')}`);
        }
      } catch (err) {
        console.error('Failed to setup chat session:', err);
      } finally {
        setLoadingSession(false);
      }
    };

    setupSession();
  }, [copilotOpen, nodeId, fetchSessions, selectSession, createSession, targetNode?.name, fetchSuggestions, t]);

  // Track whether the diagnostic/proposal trigger has already been processed
  // for the current panel open, to avoid infinite re-triggering when
  // fetchSessions (called by sendMessage's finally block) updates activeSession.
  const triggerProcessedRef = useRef(false);

  // Diagnostic / proposal trigger fan-out (same as original behaviour).
  // Runs once per copilotContext set, and is immune to re-triggering when
  // activeSession or isStreaming changes (e.g., after fetchSessions in sendMessage's finally).
  useEffect(() => {
    if (!copilotOpen || !copilotContext || triggerProcessedRef.current) return;

    // Mark as processed before conditional logic to prevent re-triggering
    // in React StrictMode's double-invocation.
    triggerProcessedRef.current = true; // eslint-disable-line react-hooks/immutability

    if (copilotContext.trigger === 'diagnostic' && copilotContext.insight) {
      const insight = copilotContext.insight;
      const prompt = `Fais un diagnostic détaillé de cette anomalie : "${insight.headline}". Détails : "${insight.detail}"`;
      sendMessage(prompt, nodeId);
    } else if (copilotContext.trigger === 'proposal' && copilotContext.proposal) {
      const proposal = copilotContext.proposal;
      const prompt = `Que penses-tu de l'action proposée : "${proposal.action}" sur "${proposal.node_id}"? Raisonnement : ${proposal.reasoning}`;
      sendMessage(prompt, nodeId);
    }
  }, [copilotOpen, copilotContext, sendMessage, nodeId]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeSession?.history, isStreaming, activeSteps, activeTools]);

  const handleSendMessage = async (text: string) => {
    await sendMessage(text, nodeId);
    fetchSuggestions(nodeId);
  };

  const handleApprove = async (id: string) => {
    setLoadingProposalId(id);
    try {
      const success = await approveProposal(id);
      if (success && activeSession) {
        await fetchSessions(nodeId);
      }
    } finally {
      setLoadingProposalId(null);
    }
  };

  const handleReject = async (id: string) => {
    setLoadingProposalId(id);
    try {
      const success = await rejectProposal(id);
      if (success && activeSession) {
        await fetchSessions(nodeId);
      }
    } finally {
      setLoadingProposalId(null);
    }
  };

  // Pending ticker: count + highest risk + focus navigation.
  const pendingCount = pendingProposalsCount();
  const highestRiskLabel = useMemo(() => {
    if (!activeSession?.history) return undefined;
    const pendings = activeSession.history.filter(
      m => m.role === 'assistant' && m.proposal?.status === 'PENDING'
    );
    const risks = pendings.map(m => (m.proposal?.risk_level || '').toLowerCase());
    if (risks.some(r => r === 'critical' || r === 'critique')) return t('prop.risk_critical');
    if (risks.some(r => r === 'high')) return t('prop.risk_high');
    if (risks.some(r => r === 'medium' || r === 'warning')) return t('prop.risk_medium');
    return t('prop.risk_low');
  }, [activeSession, t]);

  const handleFocusFirstPending = () => {
    if (!activeSession?.history) return;
    const pending = activeSession.history.find(
      m => m.role === 'assistant' && m.proposal?.status === 'PENDING'
    );
    if (!pending?.proposal?.id) return;
    const id = pending.proposal.id;
    const el = proposalRefs.current.get(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Re-trigger CSS animation by removing+adding the class.
      el.classList.remove('cp-highlight-ring');
      void el.offsetWidth;
      el.classList.add('cp-highlight-ring');
    }
  };

  // Highlight the proposal currently flagged by the ticker.
  const registerProposalRef = (proposalId: string, el: HTMLDivElement | null) => {
    proposalRefs.current.set(proposalId, el);
  };

  const history = useMemo(() => activeSession?.history || [], [activeSession?.history]);
  const turns = useMemo(() => groupByTurns(history), [history]);

  return (
    <div
      data-copilot-root
      ref={(el) => {
        // Expose root via data attribute for outside-click handling.
        if (el) el.setAttribute('data-copilot-root', '');
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="copilot-title"
      className={`fixed top-14 right-0 bottom-0 flex z-20 transition-transform duration-300 shadow-2xl bg-bg/85 backdrop-blur-2xl ${
        copilotOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'
      }`}
      style={{ width: 'var(--copilot-width-expanded)' }}
    >
      <span id="copilot-desc" className="sr-only">
        {t('copilot.aria_description')}
      </span>

      <CopilotSidebar nodeId={nodeId} />

      <div className="flex-1 flex flex-col min-w-0 bg-surface/30">
        <CopilotHeader
          nodeName={targetNode?.name}
          nodeOnline={targetNode?.state === 'CONNECTED'}
          nodeId={nodeId}
          model={activeMeta?.model || activeSession?.lastModel}
          onClose={closeCopilot}
          pendingCount={pendingCount}
        />

        {pendingCount > 0 && (
          <CopilotPendingTicker
            count={pendingCount}
            highestRiskLabel={highestRiskLabel}
            onFocusFirstPending={handleFocusFirstPending}
          />
        )}

        <div className="flex-1 overflow-y-auto cp-glass flex flex-col">
          {loadingSession ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 text-text-3 font-interface text-xs">
              <Spinner size="sm" />
              <span>{t('copilot.initializing')}</span>
            </div>
          ) : history.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-text-3 gap-3 my-auto select-none">
              <div className="w-10 h-10 rounded-lg bg-accent-info/15 border border-accent-info/25 flex items-center justify-center">
                <MessageSquare className="w-5 h-5 text-accent-info-strong animate-pulse-subtle" />
              </div>
              <span className="font-bold text-[11px] tracking-wider uppercase font-interface text-text-2">
                {t('copilot.empty_title')}
              </span>
              <span className="text-[11.5px] max-w-[260px] leading-relaxed font-normal opacity-80">
                {t('copilot.empty_description')}
              </span>
              {suggestions.length > 0 && (
                <div className="flex flex-col gap-1.5 mt-2 w-full max-w-[260px]">
                  {suggestions.slice(0, 3).map((sug, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSendMessage(sug)}
                      className="w-full text-left px-3 py-2 bg-surface-2/40 hover:bg-accent-info-soft border border-border/30 hover:border-accent-info/40 rounded-lg text-[11px] text-text-2 hover:text-text-1 transition-all duration-150"
                    >
                      {sug}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col py-3 gap-1">
              {turns.map((turnMessages, i) => (
                <CopilotTurn
                  key={i}
                  messages={turnMessages}
                  onApproveProposal={handleApprove}
                  onRejectProposal={handleReject}
                  loadingProposalId={loadingProposalId}
                  registerProposalRef={registerProposalRef}
                />
              ))}

              {/* Active agent activity indicator (explicit French status) */}
              {(isStreaming || activeSteps.length > 0) && (
                <div className="px-4 py-2 flex items-center gap-2 text-[11px] text-text-2 font-mono bg-accent-info/10 border border-accent-info/20 rounded-lg mx-3 my-2">
                  <Zap className="w-3.5 h-3.5 text-accent-info-strong animate-pulse" />
                  <Terminal className="w-3.5 h-3.5 text-accent-info-strong" />
                  <span className="inline-flex items-center gap-1 font-bold">
                    Analyse en cours...
                    {activeSteps.length > 0 && (
                      <code className="text-text-1 font-mono text-[10px]">
                        [{activeSteps[activeSteps.length - 1]}]
                      </code>
                    )}
                  </span>
                  <span className="cp-agent-typing text-accent-info-strong ml-auto">
                    <span />
                    <span />
                    <span />
                  </span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <CopilotInput
          onSend={handleSendMessage}
          disabled={loadingSession}
          isStreaming={isStreaming}
          onAbort={abortStreaming}
          suggestions={suggestions}
        />
      </div>
    </div>
  );
};
