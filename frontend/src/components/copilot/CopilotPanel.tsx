import React, { useState, useEffect, useRef } from 'react';
import { useLayoutStore } from '../../store/layoutStore';
import { useNodeStore } from '../../store/nodeStore';
import { useChatStore } from '../../store/chatStore';
import { useLocale } from '../../i18n';
import { Link } from 'react-router';
import { 
  X, 
  Send, 
  Sparkles, 
  Loader2, 
  Terminal, 
  AlertTriangle, 
  ExternalLink,
  Plus,
  MessageSquare
} from 'lucide-react';

export const CopilotPanel: React.FC = () => {
  const { isCopilotOpen, setCopilotOpen } = useLayoutStore();
  const { nodes, selectedNodeId, selectedNode } = useNodeStore();
  const { t } = useLocale();

  const { 
    sessions,
    activeSessionId,
    activeSession,
    isLoading,
    isStreaming,
    fetchSessions,
    selectSession,
    createSession,
    sendMessage,
    approveProposal,
    rejectProposal
  } = useChatStore();

  const [inputValue, setInputValue] = useState('');
  const [showSessionsDropdown, setShowSessionsDropdown] = useState(false);

  // Inline rejection state
  const [rejectingProposalId, setRejectingProposalId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Keyboard shortcut to toggle (Cmd+` or Ctrl+`)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '`') {
        e.preventDefault();
        setCopilotOpen(!isCopilotOpen);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isCopilotOpen, setCopilotOpen]);

  // Load sessions list when panel opens or node selection changes
  useEffect(() => {
    if (isCopilotOpen) {
      fetchSessions(selectedNodeId);
    }
  }, [isCopilotOpen, selectedNodeId]);

  // Focus input when opened
  useEffect(() => {
    if (isCopilotOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isCopilotOpen]);

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.history, isStreaming, isCopilotOpen]);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isStreaming) return;
    const text = inputValue.trim();
    setInputValue('');
    await sendMessage(text, selectedNodeId === 'all' ? null : selectedNodeId);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleNewSession = async () => {
    const session = await createSession(selectedNodeId === 'all' ? null : selectedNodeId, 'Copilot Session');
    if (session) {
      fetchSessions(selectedNodeId);
    }
  };

  const handleApprove = async (proposalId: string) => {
    const success = await approveProposal(proposalId);
    if (success && activeSession) {
      fetchSessions(activeSession.node_id);
    }
  };

  const handleRejectClick = (proposalId: string) => {
    setRejectingProposalId(proposalId);
    setRejectionReason('');
  };

  const handleRejectSubmit = async (proposalId: string) => {
    if (!rejectionReason.trim() || isRejecting) return;
    setIsRejecting(true);
    const success = await rejectProposal(proposalId, rejectionReason);
    if (success) {
      if (activeSession) {
        await fetchSessions(activeSession.node_id);
      }
      setRejectingProposalId(null);
      setRejectionReason('');
    }
    setIsRejecting(false);
  };

  const parseInlineCode = (text: string) => {
    const codeParts = text.split(/(`.*?`)/g);
    return codeParts.map((cp, cpIdx) => {
      if (cp.startsWith('`') && cp.endsWith('`')) {
        return (
          <code key={cpIdx} className="bg-surface-2 border border-border px-1 py-0.5 rounded font-mono text-[10px] text-ink-primary font-semibold">
            {cp.slice(1, -1)}
          </code>
        );
      }
      return cp;
    });
  };

  const parseInlineStyles = (text: string) => {
    const boldParts = text.split(/(\*\*.*?\*\*)/g);
    return boldParts.map((bp, bpIdx) => {
      if (bp.startsWith('**') && bp.endsWith('**')) {
        const innerBold = bp.slice(2, -2);
        return <strong key={bpIdx} className="font-bold text-ink-primary">{parseInlineCode(innerBold)}</strong>;
      }
      return parseInlineCode(bp);
    });
  };

  const formatMessageContent = (content: string) => {
    if (!content) return '';
    const paragraphs = content.split('\n');
    return paragraphs.map((p, pIdx) => {
      if (!p.trim()) return null;
      return <p key={pIdx} className="my-1 text-ink-secondary leading-relaxed">{parseInlineStyles(p)}</p>;
    });
  };

  const history = activeSession?.history || [];
  const nodeSessions = sessions.filter(s => s.node_id === (selectedNodeId === 'all' ? null : selectedNodeId));

  if (!isCopilotOpen) return null;

  return (
    <aside className="h-full border-l border-border bg-surface-0 transition-all duration-300 ease-in-out flex flex-col shrink-0 overflow-hidden w-[380px] z-30 relative select-none">
      
      {/* Header */}
      <div className="h-[60px] px-4 border-b border-border flex items-center justify-between shrink-0 bg-surface-0 relative z-20">
        <div className="flex items-center gap-2 overflow-hidden flex-1 mr-2">
          <div className="w-6 h-6 rounded bg-accent-subtle border border-accent-primary/20 flex items-center justify-center shrink-0">
            <Sparkles className="w-3.5 h-3.5 text-accent-primary" />
          </div>
          <div className="relative overflow-hidden flex flex-col justify-center">
            <div className="flex items-center gap-1">
              <button 
                onClick={() => setShowSessionsDropdown(!showSessionsDropdown)}
                className="text-xs font-bold text-ink-primary hover:text-accent-primary flex items-center gap-1 cursor-pointer truncate"
              >
                <span>{activeSession ? activeSession.title : 'Copilot IA'}</span>
                <span className="text-[10px] text-ink-muted">▼</span>
              </button>
            </div>
            {selectedNode && (
              <span className="text-[9px] text-ink-muted truncate">
                {selectedNode.name}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleNewSession}
            className="p-1.5 rounded hover:bg-surface-2 text-ink-muted hover:text-ink-primary transition-colors cursor-pointer"
            title="Nouvelle session"
            aria-label="Nouvelle session"
          >
            <Plus className="w-4 h-4" />
          </button>
          <Link
            to={activeSessionId ? `/chat/${activeSessionId}` : "/chat/new"}
            onClick={() => setCopilotOpen(false)}
            className="p-1.5 rounded hover:bg-surface-2 text-ink-muted hover:text-ink-primary transition-colors"
            title="Ouvrir en plein écran"
            aria-label="Ouvrir en plein écran"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </Link>
          <button
            onClick={() => {
              setShowSessionsDropdown(false);
              setCopilotOpen(false);
            }}
            className="p-1.5 rounded hover:bg-surface-2 text-ink-muted hover:text-ink-primary transition-colors cursor-pointer"
            aria-label="Fermer le panneau Copilot"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Sessions Dropdown */}
        {showSessionsDropdown && (
          <div className="absolute top-[55px] left-4 right-4 bg-surface-0 border border-border rounded-lg shadow-2xl p-2 z-50 animate-fade-in max-h-60 overflow-y-auto scrollbar-thin">
            <div className="text-[9px] font-bold text-ink-muted uppercase tracking-wider px-2 py-1 border-b border-border pb-1.5 mb-1.5 flex justify-between items-center">
              <span>Conversations récentes</span>
              <button 
                onClick={() => setShowSessionsDropdown(false)}
                className="text-[9px] text-accent-primary hover:underline cursor-pointer"
              >
                Fermer
              </button>
            </div>
            {nodeSessions.length === 0 ? (
              <div className="p-4 text-center text-xs text-ink-muted italic">
                Aucune session trouvée.
              </div>
            ) : (
              <div className="space-y-1">
                {nodeSessions.map(s => (
                  <button
                    key={s.id}
                    onClick={() => {
                      selectSession(s.id);
                      setShowSessionsDropdown(false);
                    }}
                    className={`w-full text-left p-2 rounded text-xs flex items-center gap-2 hover:bg-surface-1 transition-colors ${
                      activeSessionId === s.id ? 'bg-accent-subtle text-accent-primary font-bold' : 'text-ink-secondary'
                    }`}
                  >
                    <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate flex-1">{s.title}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4 scrollbar-thin">
        {isLoading && history.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-2">
            <Loader2 className="w-6 h-6 animate-spin text-accent-primary" />
            <span className="text-xs text-ink-muted font-bold">{t('chat.loading')}</span>
          </div>
        ) : (
          <>
            {/* Welcome block */}
            {history.length === 0 && (
              <div className="self-start bg-surface-1/40 border border-border rounded p-3 text-xs leading-relaxed text-ink-secondary max-w-[85%] animate-fade-up">
                <div className="flex items-center gap-1.5 mb-1 text-[10px] font-bold text-accent-primary uppercase tracking-wider">
                  <Sparkles className="w-3 h-3 animate-pulse" />
                  <span>{t('chat.copilot')}</span>
                </div>
                <p>{nodes.length > 1 ? t('chat.welcome_multi') : t('chat.welcome')}</p>
              </div>
            )}

            {history.map((msg, idx) => {
              const isUser = msg.role === 'user';
              return (
                <div
                  key={idx}
                  className={`flex flex-col max-w-[85%] rounded p-3 text-xs leading-relaxed transition-all duration-200 animate-fade-up ${
                    isUser
                      ? "self-end bg-accent-subtle border border-accent-primary/10 text-ink-primary"
                      : "self-start bg-surface-1/40 border border-border text-ink-secondary"
                  }`}
                >
                  {/* Speaker label */}
                  <div className="flex items-center gap-1.5 mb-1 text-[9px] font-bold text-ink-muted uppercase tracking-wider">
                    {isUser ? (
                      <span>{t('chat.user')}</span>
                    ) : (
                      <span className="flex items-center gap-1 text-accent-primary">
                        <Sparkles className="w-3 h-3" />
                        <span>{t('chat.copilot')}</span>
                      </span>
                    )}
                  </div>

                  {/* Message Content */}
                  <div className="space-y-1">{formatMessageContent(msg.content)}</div>

                  {/* Action Proposal Rendering */}
                  {msg.proposal && (
                    <div className="mt-3 pt-3 border-t border-border flex flex-col gap-2.5">
                      <div className="flex items-center gap-1.5">
                        <Terminal className="w-3.5 h-3.5 text-accent-primary" />
                        <span className="font-bold text-[9px] text-ink-primary uppercase tracking-wider">
                          {t('chat.proposal_title')}
                        </span>
                      </div>

                      <div className="p-2 rounded bg-[#06060a] border border-border font-mono text-[10px] text-success/90 overflow-x-auto whitespace-pre-wrap select-all">
                        {msg.proposal.action}
                      </div>

                      {msg.proposal.reasoning && (
                        <p className="text-[9px] text-ink-muted italic">
                          {msg.proposal.reasoning}
                        </p>
                      )}

                      <div className="flex flex-col gap-2 mt-1 border-t border-border/40 pt-2">
                        <div className="flex items-center gap-1.5">
                          <AlertTriangle className={`w-3 h-3 ${
                            msg.proposal.risk_level === 'HIGH' ? 'text-danger animate-pulse' :
                            msg.proposal.risk_level === 'MEDIUM' ? 'text-warning' : 'text-success'
                          }`} />
                          <span className="text-[9px] font-bold text-ink-muted uppercase">
                            {t('chat.risk_level', { level: msg.proposal.risk_level })}
                          </span>
                        </div>

                        {/* Proposal Actions / Rejection inputs */}
                        <div className="flex flex-col gap-2 mt-1">
                          {rejectingProposalId === msg.proposal.id ? (
                            <div className="flex flex-col gap-1.5 w-full">
                              <input 
                                type="text" 
                                placeholder={t('prop.reject_reason_placeholder')} 
                                value={rejectionReason}
                                onChange={e => setRejectionReason(e.target.value)}
                                className="input py-1 px-2 text-[10.5px]"
                                autoFocus
                              />
                              <div className="flex justify-end gap-1.5">
                                <button 
                                  onClick={() => setRejectingProposalId(null)}
                                  disabled={isRejecting}
                                  className="btn btn-secondary py-0.5 px-2 text-[9px]"
                                >
                                  Annuler
                                </button>
                                <button 
                                  onClick={() => handleRejectSubmit(msg.proposal!.id)}
                                  disabled={isRejecting || !rejectionReason.trim()}
                                  className="btn btn-danger py-0.5 px-2 text-[9px] flex items-center gap-1"
                                >
                                  {isRejecting && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
                                  <span>{t('prop.btn.reject')}</span>
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => handleRejectClick(msg.proposal!.id)}
                                className="btn btn-secondary py-0.5 px-2 text-[10px]"
                              >
                                {t('chat.btn.reject')}
                              </button>
                              <button
                                onClick={() => handleApprove(msg.proposal!.id)}
                                className="btn btn-primary py-0.5 px-2 text-[10px]"
                              >
                                {t('chat.btn.approve')}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {/* Streaming Message Indicator */}
            {isStreaming && history.length > 0 && history[history.length - 1].role === 'user' && (
              <div className="self-start bg-surface-1/40 border border-border rounded p-3 text-xs leading-relaxed text-ink-secondary max-w-[85%] animate-fade-up">
                <div className="flex items-center gap-1.5 mb-1 text-[9px] font-bold text-accent-primary uppercase tracking-wider">
                  <Sparkles className="w-3 h-3 animate-spin" />
                  <span>{t('chat.copilot')}</span>
                </div>
                <div className="flex items-center gap-1 py-1">
                  <span className="w-1.5 h-3 bg-accent-primary animate-pulse" />
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input Form */}
      <div className="p-3 border-t border-border bg-surface-0 shrink-0 bg-surface-0 relative z-10">
        <div className="relative rounded-lg border border-border bg-[#06060a] focus-within:border-accent-primary transition-all duration-150 p-2 shadow-sm">
          <textarea
            ref={inputRef}
            rows={2}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('chat.placeholder')}
            className="w-full bg-transparent border-0 outline-hidden resize-none text-xs text-ink-primary placeholder-ink-muted py-1 pr-10 focus:ring-0 leading-relaxed font-sans"
            disabled={isStreaming}
          />
          <div className="flex justify-between items-center mt-1 pt-1.5 border-t border-border/40">
            <span className="text-[9px] text-ink-muted select-none flex items-center gap-1">
              <span>{t('chat.shift_enter')}</span>
            </span>
            <button
              onClick={handleSendMessage}
              disabled={isStreaming || !inputValue.trim()}
              className="btn btn-primary p-1.5"
            >
              {isStreaming ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
};
