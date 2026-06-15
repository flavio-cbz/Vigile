import React, { useEffect, useRef, useState } from 'react';
import { useUiStore } from '../../store/uiStore';
import { useChatStore } from '../../store/chatStore';
import { useNodeStore } from '../../store/nodeStore';
import { CopilotHeader } from './CopilotHeader';
import { CopilotMessage } from './CopilotMessage';
import { CopilotInput } from './CopilotInput';
import { Spinner } from '../primitives/Spinner';
import { MessageSquare } from 'lucide-react';

export const CopilotPanel: React.FC = () => {
  const { copilotOpen, copilotContext, closeCopilot } = useUiStore();
  const { nodes } = useNodeStore();
  const {
    activeSession,
    isStreaming,
    sendMessage,
    createSession,
    fetchSessions,
    selectSession,
    approveProposal,
    rejectProposal,
  } = useChatStore();

  const [loadingSession, setLoadingSession] = useState(false);
  const [loadingProposalId, setLoadingProposalId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const nodeId = copilotContext?.node_id || null;
  const targetNode = nodes.find((n) => n.id === nodeId);

  useEffect(() => {
    if (!copilotOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        closeCopilot();
      }
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

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeSession?.history, isStreaming]);

  useEffect(() => {
    if (!copilotOpen) return;

    const setupSession = async () => {
      setLoadingSession(true);
      try {
        await fetchSessions(nodeId);

        const { sessions: latestSessions } = useChatStore.getState();
        const nodeSessions = latestSessions.filter((s) => s.node_id === nodeId);
        if (nodeSessions.length > 0) {
          selectSession(nodeSessions[0].id);
        } else {
          await createSession(nodeId, `Focus : ${targetNode?.name || 'Système'}`);
        }
      } catch (err) {
        console.error('Failed to setup chat session:', err);
      } finally {
        setLoadingSession(false);
      }
    };

    setupSession();
  }, [copilotOpen, nodeId, fetchSessions, selectSession, createSession, targetNode?.name]);

  useEffect(() => {
    if (copilotOpen && activeSession && !loadingSession && !isStreaming) {
      const triggerDiagnostic = async () => {
        if (copilotContext?.trigger === 'diagnostic' && copilotContext.insight) {
          const insight = copilotContext.insight;
          const prompt = `Fais un diagnostic détaillé de cette anomalie : "${insight.headline}". Détails : "${insight.detail}"`;

          // Only trigger if we don't already have messages related to this in history
          const alreadySent = activeSession.history?.some(
            (msg) => msg.role === 'user' && msg.content.includes(insight.headline)
          );

          if (!alreadySent) {
            await sendMessage(prompt, nodeId);
          }
        } else if (copilotContext?.trigger === 'proposal' && copilotContext.proposal) {
          const proposal = copilotContext.proposal;
          const prompt = `Que penses-tu de l'action proposée : "${proposal.action}" sur "${proposal.node_id}"? Raisonnement : ${proposal.reasoning}`;

          const alreadySent = activeSession.history?.some(
            (msg) => msg.role === 'user' && msg.content.includes(proposal.action)
          );

          if (!alreadySent) {
            await sendMessage(prompt, nodeId);
          }
        }
      };

      triggerDiagnostic();
    }
  }, [copilotOpen, activeSession, loadingSession, copilotContext, sendMessage, nodeId, isStreaming]);

  const handleSendMessage = async (text: string) => {
    await sendMessage(text, nodeId);
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

  const messages = activeSession?.history || [];

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="copilot-title"
      aria-describedby="copilot-desc"
      className={`fixed top-14 right-0 bottom-0 w-full md:w-[var(--copilot-width,380px)] border-l border-border bg-surface/85 backdrop-blur-xl flex flex-col z-20 transition-transform duration-300 shadow-2xl ${
        copilotOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'
      }`}
    >
      <span id="copilot-desc" className="sr-only">
        Panneau d'assistant virtuel Vigile pour vous aider à diagnostiquer et administrer votre flotte de serveurs.
      </span>
      <CopilotHeader nodeName={targetNode?.name} onClose={closeCopilot} />

      <div className="flex-1 overflow-y-auto no-scrollbar bg-surface/40 flex flex-col">
        {loadingSession ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-text-3 font-interface text-xs">
            <Spinner size="sm" />
            <span>INITIALISATION DES SYSTÈMES...</span>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-text-3 font-sans gap-2 my-auto select-none">
            <MessageSquare className="w-8 h-8 opacity-30 text-accent animate-pulse" />
            <span className="font-bold text-[10px] tracking-wider uppercase font-interface">
              Aucune conversation en cours
            </span>
            <span className="text-[10.5px] max-w-[200px] leading-relaxed font-normal">
              Posez une question sur l'état de vos nodes, ou demandez un diagnostic.
            </span>
          </div>
        ) : (
          <div className="flex-col">
            {messages.map((msg, i) => (
              <CopilotMessage
                key={i}
                message={msg}
                onApproveProposal={handleApprove}
                onRejectProposal={handleReject}
                loadingProposal={loadingProposalId === msg.proposal?.id}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <CopilotInput onSend={handleSendMessage} disabled={loadingSession || isStreaming} />
    </div>
  );
};
