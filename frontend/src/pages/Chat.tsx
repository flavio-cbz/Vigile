import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router';
import { useNodeStore } from '../store/nodeStore';
import { useChatStore } from '../store/chatStore';
import { useLocale } from '../i18n';
import { 
  ArrowLeft,
  Send, 
  Sparkles, 
  Loader2, 
  Terminal, 
  AlertTriangle, 
  XOctagon,
  Edit2,
  CheckSquare,
  Server,
  Trash2,
  X,
  Copy
} from 'lucide-react';

export const Chat: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useLocale();
  
  const { nodes, selectedNodeId } = useNodeStore();
  const { 
    sessions,
    activeSessionId,
    activeSession,
    isLoading,
    isStreaming,
    fetchSessions,
    selectSession,
    sendMessage,
    updateSession,
    deleteSession,
    approveProposal,
    rejectProposal
  } = useChatStore();
  
  const [inputValue, setInputValue] = useState('');
  
  // Session details
  const [chatNodeId, setChatNodeId] = useState<string>('all');
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleInput, setTitleInput] = useState('');
  
  // Rejection state
  const [rejectingProposal, setRejectingProposal] = useState<{ msgIdx: number; proposalId: string } | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);
  
  // Copy state
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load sessions list on mount
  useEffect(() => {
    fetchSessions();
  }, []);

  // Sync route param with chatStore selection
  useEffect(() => {
    if (id && id !== 'new') {
      selectSession(id);
    } else {
      selectSession(null);
    }
  }, [id, sessions]);

  // Handle auto-routing when a new session is created and activeSessionId gets generated
  useEffect(() => {
    if (id === 'new' && activeSessionId) {
      navigate(`/chat/${activeSessionId}`, { replace: true });
    }
  }, [activeSessionId, id]);

  // Sync associated server selection
  useEffect(() => {
    if (activeSession) {
      setChatNodeId(activeSession.node_id || 'all');
    } else {
      setChatNodeId(selectedNodeId || 'all');
    }
  }, [activeSession, selectedNodeId]);

  // Scroll to bottom when history or streaming changes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.history, isStreaming]);

  const handleStartEditTitle = () => {
    if (activeSession) {
      setTitleInput(activeSession.title);
      setIsEditingTitle(true);
    }
  };

  const handleSaveTitle = async () => {
    if (activeSession && titleInput.trim()) {
      await updateSession(activeSession.id, titleInput.trim(), chatNodeId);
    }
    setIsEditingTitle(false);
  };

  const handleNodeChange = async (newNodeId: string) => {
    setChatNodeId(newNodeId);
    if (activeSession) {
      await updateSession(activeSession.id, activeSession.title, newNodeId === 'all' ? null : newNodeId);
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isStreaming) return;
    const text = inputValue.trim();
    setInputValue('');
    await sendMessage(text, chatNodeId === 'all' ? null : chatNodeId);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCopyCode = (code: string, blockIndex: number) => {
    navigator.clipboard.writeText(code);
    setCopiedId(String(blockIndex));
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleApproveProposal = async (proposalId: string) => {
    const success = await approveProposal(proposalId);
    if (success && activeSession) {
      fetchSessions(activeSession.node_id);
    }
  };

  const handleRejectClick = (msgIdx: number, proposalId: string) => {
    setRejectingProposal({ msgIdx, proposalId });
    setRejectionReason('');
  };

  const handleRejectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingProposal || isRejecting) return;
    setIsRejecting(true);
    const success = await rejectProposal(rejectingProposal.proposalId, rejectionReason);
    if (success) {
      if (activeSession) {
        await fetchSessions(activeSession.node_id);
      }
      setRejectingProposal(null);
      setRejectionReason('');
    }
    setIsRejecting(false);
  };

  const handleDeleteChat = async () => {
    if (activeSession) {
      if (confirm(t('plugins.confirm_uninstall'))) { // simple confirmation, fallback for session delete
        await deleteSession(activeSession.id);
        navigate('/chat/new');
      }
    }
  };

  // Inline formatting helper
  const parseInlineCode = (text: string) => {
    const codeParts = text.split(/(`.*?`)/g);
    return codeParts.map((cp, cpIdx) => {
      if (cp.startsWith('`') && cp.endsWith('`')) {
        return (
          <code key={cpIdx} className="bg-surface-2 border border-border px-1 py-0.5 rounded font-mono text-[11px] text-ink-primary font-semibold">
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
    const parts = content.split(/(```[\s\S]*?```)/g);
    
    return parts.map((part, index) => {
      if (part.startsWith('```')) {
        const match = part.match(/```(\w*)\n([\s\S]*?)```/);
        const lang = match ? match[1] : '';
        const code = match ? match[2] : part.replace(/```/g, '');
        return (
          <div key={index} className="my-3 border border-border rounded bg-[#06060a] overflow-hidden font-mono text-[11px] shadow-md max-w-full">
            <div className="flex justify-between items-center px-3 py-1.5 bg-surface-1 border-b border-border text-[9px] text-ink-muted">
              <span className="uppercase font-bold tracking-wider">{lang || 'code'}</span>
              <button
                onClick={() => handleCopyCode(code.trim(), index)}
                className="hover:text-ink-primary transition-colors cursor-pointer flex items-center gap-1"
              >
                <Copy className="w-3 h-3" />
                <span>{copiedId === String(index) ? t('chat.copied') : t('chat.copy')}</span>
              </button>
            </div>
            <pre className="p-3 overflow-x-auto text-success/90 whitespace-pre">{code.trim()}</pre>
          </div>
        );
      } else {
        const paragraphs = part.split('\n\n');
        return paragraphs.map((p, pIdx) => {
          if (!p.trim()) return null;
          
          if (p.trim().startsWith('- ') || p.trim().startsWith('* ')) {
            const items = p.split(/\n[-*] /);
            return (
              <ul key={`${index}-${pIdx}`} className="list-disc pl-4 my-2 flex flex-col gap-1 text-ink-secondary">
                {items.map((item, itemIdx) => {
                  let text = item;
                  if (itemIdx === 0) {
                    text = item.replace(/^[-*] /, '');
                  }
                  return <li key={itemIdx}>{parseInlineStyles(text)}</li>;
                })}
              </ul>
            );
          }

          if (/^\d+\.\s/.test(p.trim())) {
            const items = p.split(/\n\d+\.\s/);
            return (
              <ol key={`${index}-${pIdx}`} className="list-decimal pl-4 my-2 flex flex-col gap-1 text-ink-secondary">
                {items.map((item, itemIdx) => {
                  let text = item;
                  if (itemIdx === 0) {
                    text = item.replace(/^\d+\.\s/, '');
                  }
                  return <li key={itemIdx}>{parseInlineStyles(text)}</li>;
                })}
              </ol>
            );
          }
          
          return <p key={`${index}-${pIdx}`} className="my-1.5 text-ink-secondary leading-relaxed">{parseInlineStyles(p)}</p>;
        });
      }
    });
  };

  const getWelcomeMessage = () => {
    return nodes.length > 1 ? t('chat.welcome_multi') : t('chat.welcome');
  };

  const history = activeSession?.history || [];

  return (
    <div className="flex-1 flex flex-col h-full bg-background relative overflow-hidden animate-fade-in">
      {/* Title Header */}
      <div className="h-[60px] px-6 border-b border-border bg-surface-0 flex items-center justify-between shrink-0 z-10">
        <div className="flex items-center gap-4 flex-1">
          <Link
            to="/"
            className="btn btn-secondary py-1.5 px-3 flex items-center justify-center"
            title="Retour au Tableau de Bord"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>

          {/* Chat Title Input / Edit */}
          <div className="flex items-center gap-2 max-w-[400px] flex-1">
            {isEditingTitle ? (
              <div className="flex items-center gap-1.5 w-full">
                <input
                  type="text"
                  value={titleInput}
                  onChange={(e) => setTitleInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSaveTitle()}
                  className="input py-1 text-xs w-full"
                  autoFocus
                />
                <button
                  onClick={handleSaveTitle}
                  className="btn btn-primary p-1.5"
                >
                  <CheckSquare className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 group max-w-full">
                <span className="text-xs font-bold text-ink-primary truncate max-w-[280px]">
                  {activeSession ? activeSession.title : t('chat.title_new')}
                </span>
                {activeSession && (
                  <>
                    <button
                      onClick={handleStartEditTitle}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-surface-2 text-ink-muted hover:text-ink-primary transition-all duration-150 cursor-pointer"
                      title={t('chat.title_edit')}
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                    <button
                      onClick={handleDeleteChat}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-danger-subtle text-ink-muted hover:text-danger transition-all duration-150 cursor-pointer ml-1"
                      title="Supprimer la conversation"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Server Bind Dropdown */}
        {nodes.length > 0 && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs text-ink-muted font-bold mr-2">
              <Server className="w-3.5 h-3.5" />
              <span>{t('chat.associate')}</span>
            </div>
            <select
              value={chatNodeId}
              onChange={(e) => handleNodeChange(e.target.value)}
              className="select text-xs font-bold py-1.5"
            >
              <option value="all">{t('chat.all_servers')}</option>
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Main Discussion Feed */}
      <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-6 scrollbar-thin">
        {isLoading && history.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-accent-primary" />
            <span className="text-xs text-ink-muted font-bold">{t('chat.loading')}</span>
          </div>
        ) : (
          <>
            {/* Welcome message */}
            {history.length === 0 && (
              <div className="self-start bg-surface-0 border border-border rounded-xl p-4 text-xs shadow-xs text-ink-secondary max-w-[85%] sm:max-w-[75%] animate-fade-up">
                <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold text-accent-primary uppercase tracking-wider">
                  <Sparkles className="w-3 h-3 animate-pulse" />
                  <span>{t('chat.copilot')}</span>
                </div>
                <p className="leading-relaxed">{getWelcomeMessage()}</p>
              </div>
            )}

            {history.map((msg, idx) => {
              const isUser = msg.role === 'user';
              return (
                <div
                  key={idx}
                  className={`flex flex-col max-w-[85%] sm:max-w-[75%] rounded-xl p-4 text-xs border transition-all duration-200 animate-fade-up ${
                    isUser
                      ? "self-end bg-accent-subtle border-accent-primary/20 text-ink-primary"
                      : "self-start bg-surface-0 border-border text-ink-secondary"
                  }`}
                >
                  {/* Speaker Label */}
                  <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                    {isUser ? (
                      <span>{t('chat.user')}</span>
                    ) : (
                      <span className="flex items-center gap-1 text-accent-primary">
                        <Sparkles className="w-3 h-3" />
                        <span>{t('chat.copilot')}</span>
                      </span>
                    )}
                  </div>

                  {/* Render formatted message content */}
                  <div className="space-y-1">{formatMessageContent(msg.content)}</div>

                  {/* Action Proposal Inside Bubble */}
                  {msg.proposal && (
                    <div className="mt-4 pt-4 border-t border-border/60 flex flex-col gap-3">
                      <div className="flex items-center gap-1.5">
                        <Terminal className="w-4 h-4 text-accent-primary" />
                        <span className="font-bold text-[10px] text-ink-primary uppercase tracking-wider">
                          {t('chat.proposal_title')}
                        </span>
                      </div>

                      <div className="p-3 rounded-lg bg-[#06060a] border border-border font-mono text-[10px] text-success/90 overflow-x-auto whitespace-pre-wrap select-all">
                        {msg.proposal.action}
                      </div>

                      {msg.proposal.reasoning && (
                        <p className="text-[11px] text-ink-muted italic">
                          {msg.proposal.reasoning}
                        </p>
                      )}

                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/40">
                        <div className="flex items-center gap-1.5">
                          <AlertTriangle className={`w-3.5 h-3.5 ${
                            msg.proposal.risk_level === 'HIGH' ? 'text-danger animate-pulse' :
                            msg.proposal.risk_level === 'MEDIUM' ? 'text-warning' : 'text-success'
                          }`} />
                          <span className="text-[10px] font-bold text-ink-muted uppercase">
                            {t('chat.risk_level', { level: msg.proposal.risk_level })}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          {/* If proposal status isn't explicitly executed/rejected, we show accept/reject */}
                          {/* Since proposals come from streaming history, we resolve status from the action logs or details if available */}
                          {/* In useChatStore, proposals have status if loaded, let's fall back to rendering actions if we don't have it marked completed */}
                          <button
                            onClick={() => handleRejectClick(idx, msg.proposal!.id)}
                            className="btn btn-secondary py-1 px-2.5 text-[10.5px]"
                          >
                            {t('chat.btn.reject')}
                          </button>
                          <button
                            onClick={() => handleApproveProposal(msg.proposal!.id)}
                            className="btn btn-primary py-1 px-2.5 text-[10.5px]"
                          >
                            {t('chat.btn.approve')}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            
            {/* Streaming Message Indicator */}
            {isStreaming && history.length > 0 && history[history.length - 1].role === 'user' && (
              <div className="self-start bg-surface-0 border border-border rounded-xl p-4 text-xs shadow-xs text-ink-secondary max-w-[85%] sm:max-w-[75%] animate-fade-up">
                <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold text-accent-primary uppercase tracking-wider">
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

      {/* Floating Input Area */}
      <div className="p-4 px-6 border-t border-border bg-surface-0 shrink-0">
        <div className="max-w-4xl mx-auto relative rounded-xl border border-border bg-[#06060a] focus-within:border-accent-primary transition-all duration-150 p-2.5 shadow-lg">
          <textarea
            ref={inputRef}
            rows={2}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('chat.placeholder')}
            className="w-full bg-transparent border-0 outline-hidden resize-none text-xs text-ink-primary placeholder-ink-muted py-1 pr-12 focus:ring-0 leading-relaxed font-sans"
            disabled={isStreaming}
          />
          <div className="flex justify-between items-center mt-1.5 pt-2 border-t border-border/40">
            <span className="text-[10px] text-ink-muted select-none flex items-center gap-1">
              <span>{t('chat.shift_enter')}</span>
            </span>
            <button
              onClick={handleSendMessage}
              disabled={isStreaming || !inputValue.trim()}
              className="btn btn-primary p-2"
            >
              {isStreaming ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* MODAL: REJECT REASON INPUT */}
      {rejectingProposal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-in select-none">
          <div className="w-full max-w-md card p-6 shadow-2xl space-y-5 animate-fade-up">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-1.5">
                <XOctagon className="w-4 h-4 text-danger" />
                <span>{t('prop.reject_reason_title')}</span>
              </h3>
              <button
                onClick={() => setRejectingProposal(null)}
                className="text-ink-muted hover:text-ink-primary cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleRejectSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                  {t('prop.reject_reason_title')}
                </label>
                <textarea
                  required
                  rows={3}
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  placeholder={t('prop.reject_reason_placeholder')}
                  className="input resize-none"
                  autoFocus
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setRejectingProposal(null)}
                  disabled={isRejecting}
                  className="btn btn-secondary text-xs"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={isRejecting}
                  className="btn btn-danger text-xs flex items-center gap-1.5"
                >
                  {isRejecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
                  <span>{t('prop.btn.reject')}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
