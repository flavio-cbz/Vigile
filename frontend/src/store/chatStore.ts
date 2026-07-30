import { create } from 'zustand';
import { useAuthStore } from './authStore';
import { useToastStore } from './useToastStore';
import { useLocaleStore } from './localeStore';
import { api } from '../hooks/useApi';
import { t } from '../i18n';
import type { ProposalActionResponse } from '../types';
import type { ActionProposal } from './uiStore';

export interface ToolResult {
  tool: string;
  nodeId?: string | null;
  durationMs?: number;
  success: boolean;
  proposalId?: string;
  /** Optional preview of tool output (truncated). */
  preview?: string;
}

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  /** Stable identifier for reaction/copy/highlight operations (assigned client-side). */
  id?: string;
  /** LLM model that produced the assistant turn (from SSE meta event). */
  model?: string;
  /** Approximate token count for the assistant turn (input + output). */
  tokens?: number;
  /** Latency in ms between user send and first assistant token / done event. */
  latencyMs?: number;
  /** Tools invoked while producing this message (ReAct loop). */
  tools?: ToolResult[];
  /** Optional inline action proposal attached to the assistant message. */
  proposal?: {
    id: string;
    action: string;
    risk_level: string;
    reasoning?: string;
    target?: string;
    status?: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED';
    params?: Record<string, unknown>;
  };
  /** For role='tool': name of the tool that produced this system message. */
  name?: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  node_id: string | null;
  title: string;
  history: Message[];
  /** Last known LLM model used on this session (most recent meta event). */
  lastModel?: string;
  created_at: number;
  updated_at: number;
}

export interface Proposal {
  id: string;
  node_id: string;
  action: string;
  params: Record<string, unknown>;
  reasoning: string;
  risk_level: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED';
  created_by: string;
  created_at: number;
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  activeSession: ChatSession | null;
  isLoading: boolean;
  isStreaming: boolean;
  activeSteps: string[];
  /** Tools reported by SSE tool_result events during the current stream. */
  activeTools: ToolResult[];
  /** Most recent meta from the SSE stream (model + node_id). */
  activeMeta: { model?: string; nodeId?: string | null } | null;
  suggestions: string[];
  _abortController?: AbortController;
  fetchSessions: (nodeId?: string | null) => Promise<void>;
  selectSession: (sessionId: string | null) => void;
  createSession: (nodeId?: string | null, title?: string) => Promise<ChatSession | null>;
  deleteSession: (sessionId: string) => Promise<void>;
  sendMessage: (content: string, nodeId?: string | null) => Promise<void>;
  updateSession: (sessionId: string, title: string, nodeId: string | null) => Promise<void>;
  approveProposal: (proposalId: string) => Promise<boolean>;
  rejectProposal: (proposalId: string, reason?: string) => Promise<boolean>;
  abortStreaming: () => void;
  fetchSuggestions: (nodeId?: string | null) => Promise<void>;
  /** Derived count of PENDING proposals in the active session's history. */
  pendingProposalsCount: () => number;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  activeSession: null,
  isLoading: false,
  isStreaming: false,
  activeSteps: [],
  activeTools: [],
  activeMeta: null,
  suggestions: [],

  abortStreaming: () => {
    const { _abortController } = get();
    if (_abortController) {
      _abortController.abort();
      set({ isStreaming: false });
    }
  },

  fetchSessions: async (nodeId) => {
    set({ isLoading: true });
    try {
      const url = nodeId && nodeId !== 'all'
        ? `/api/chat/sessions?node_id=${nodeId}`
        : '/api/chat/sessions';
      const data = await api<ChatSession[]>(url);
      if (data) {
        set({ sessions: data });
        const { activeSessionId } = get();
        if (activeSessionId) {
          const active = data.find(s => s.id === activeSessionId) || null;
          set({ activeSession: active });
        }
      }
    } catch (err) {
      console.error('Failed to fetch chat sessions:', err);
    } finally {
      set({ isLoading: false });
    }
  },

  selectSession: (sessionId) => {
    const { sessions } = get();
    const active = sessions.find(s => s.id === sessionId) || null;
    set({ activeSessionId: sessionId, activeSession: active });
  },

  createSession: async (nodeId, title) => {
    const defaultTitle = title || 'Nouvelle conversation';
    const cleanNodeId = nodeId === 'all' ? null : nodeId;
    const body = {
      title: defaultTitle,
      node_id: cleanNodeId,
      history: []
    };

    try {
      const newSession = await api<ChatSession>('/api/chat/sessions', {
        method: 'POST',
        body: JSON.stringify(body)
      });

      if (newSession) {
        set(state => {
          const exists = state.sessions.some(s => s.id === newSession.id);
          const updatedSessions = exists
            ? state.sessions.map(s => s.id === newSession.id ? newSession : s)
            : [newSession, ...state.sessions];
          return {
            sessions: updatedSessions,
            activeSessionId: newSession.id,
            activeSession: newSession
          };
        });
        return newSession;
      }
    } catch {
      useToastStore.getState().addToast('error', t('chat.toast.ai_error'), t('chat.toast.create_error'));
    }
    return null;
  },

  deleteSession: async (sessionId) => {
    try {
      const res = await api<{ success: boolean }>(`/api/chat/sessions/${sessionId}`, {
        method: 'DELETE'
      });
      if (res?.success) {
        set(state => {
          const filtered = state.sessions.filter(s => s.id !== sessionId);
          const nextActiveId = state.activeSessionId === sessionId ? null : state.activeSessionId;
          const nextActive = nextActiveId ? filtered.find(s => s.id === nextActiveId) || null : null;
          return {
            sessions: filtered,
            activeSessionId: nextActiveId,
            activeSession: nextActive
          };
        });
        useToastStore.getState().addToast('success', t('chat.toast.success'), t('chat.toast.session_deleted'));
      }
    } catch {
      useToastStore.getState().addToast('error', t('chat.toast.error'), t('chat.toast.session_delete_error'));
    }
  },

  sendMessage: async (content, nodeId) => {
    const { activeSession, createSession, isStreaming } = get();
    if (isStreaming || !content.trim()) return;

    let currentSession = activeSession;
    if (!currentSession) {
      currentSession = await createSession(nodeId, content.substring(0, 30));
      if (!currentSession) return;
    }

    // Optimistic UI update: append user message
    const userMessage: Message = { role: 'user', content };
    const baseHistory = [...(currentSession.history || []), userMessage];

    set(state => {
      if (!state.activeSession) return {};
      const updatedSession = { ...state.activeSession, history: baseHistory };
      return {
        isStreaming: true,
        activeSteps: [],
        activeSession: updatedSession,
        sessions: state.sessions.map(s => s.id === updatedSession.id ? updatedSession : s)
      };
    });

    const token = useAuthStore.getState().accessToken;
    const locale = useLocaleStore.getState().locale;
    const body = {
      message: content,
      node_id: currentSession.node_id,
      session_id: currentSession.id,
      history: baseHistory.slice(0, -1) // send everything except the last optimistic user message
    };

    const abortController = new AbortController();
    set({ _abortController: abortController });
    const fetchTimeout = window.setTimeout(() => abortController.abort(), 30000);
    let wasRateLimited = false;

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'Accept-Language': locale
        },
        signal: abortController.signal,
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        if (response.status === 429) wasRateLimited = true;
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('ReadableStream non disponible');
      }

      const assistantMessage: Message = { role: 'assistant', content: '', tools: [] };
      const sessionId = currentSession.id;
      const sendStartTs = performance.now();
      let firstTokenTs: number | null = null;

      const updateAssistantMessage = () => {
        const state = get();
        if (!state.activeSession || state.activeSession.id !== sessionId) return;
        const currentHistory = state.activeSession.history;
        const updatedHistory = currentHistory.length > 0
          ? [...currentHistory.slice(0, -1), { ...assistantMessage }]
          : [{ ...assistantMessage }];
        const updatedSession = { ...state.activeSession, history: updatedHistory };
        set({
          activeSession: updatedSession,
          sessions: state.sessions.map(s => s.id === updatedSession.id ? updatedSession : s)
        });
      };

      // Throttle per-token setState via requestAnimationFrame to avoid
      // re-rendering the CopilotPanel for every SSE token (30-50/s → max 60/s).
      let rafPending = false;
      let rafId: number | null = null;

      const scheduleUpdate = () => {
        if (rafPending) return;
        rafPending = true;
        rafId = requestAnimationFrame(() => {
          rafPending = false;
          rafId = null;
          updateAssistantMessage();
        });
      };

      const flushUpdate = () => {
        if (rafPending && rafId !== null) {
          cancelAnimationFrame(rafId);
          rafPending = false;
          rafId = null;
          updateAssistantMessage();
        }
      };

      set(state => {
        if (!state.activeSession) return {};
        const withPlaceholder = [...(state.activeSession.history || []), { ...assistantMessage }];
        const updatedSession = { ...state.activeSession, history: withPlaceholder };
        return {
          activeSteps: [],
          activeTools: [],
          activeMeta: null,
          activeSession: updatedSession,
          sessions: state.sessions.map(s => s.id === updatedSession.id ? updatedSession : s)
        };
      });

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;

          try {
            const rawJson = trimmed.substring(5).trim();
            if (!rawJson) continue;
            const data = JSON.parse(rawJson);

            if (data.type === 'meta') {
              set({
                activeMeta: { model: data.model, nodeId: data.node_id ?? null }
              });
              if (data.model) {
                assistantMessage.model = data.model;
                updateAssistantMessage();
                // Update the session's lastModel as well.
                const state = get();
                if (state.activeSession) {
                  const updated = { ...state.activeSession, lastModel: data.model };
                  set({
                    activeSession: updated,
                    sessions: state.sessions.map(s => s.id === updated.id ? updated : s)
                  });
                }
              }
            } else if (data.type === 'token') {
              if (firstTokenTs === null) {
                firstTokenTs = performance.now();
                assistantMessage.latencyMs = Math.round(firstTokenTs - sendStartTs);
              }
              assistantMessage.content += data.content;
              scheduleUpdate();
            } else if (data.type === 'proposal' || data.type === 'proposal_needed') {
              assistantMessage.proposal = {
                id: data.proposal_id,
                action: data.action,
                risk_level: data.risk_level,
                reasoning: data.reasoning,
                target: data.target || (data.params?.container_id || data.params?.container || data.params?.service || ''),
                status: data.status || 'PENDING',
                params: data.params,
              };
              updateAssistantMessage();
            } else if (data.type === 'tool_executing') {
              set(state => ({
                activeSteps: [...state.activeSteps, data.tool]
              }));
            } else if (data.type === 'tool_result') {
              const tool: ToolResult = {
                tool: data.tool,
                nodeId: data.node_id ?? null,
                durationMs: typeof data.duration_ms === 'number' ? data.duration_ms : undefined,
                success: !!data.success,
                proposalId: data.proposal_id,
              };
              set(state => ({ activeTools: [...state.activeTools, tool] }));
              if (!assistantMessage.tools) assistantMessage.tools = [];
              assistantMessage.tools.push(tool);
              updateAssistantMessage();
            } else if (data.type === 'error') {
              useToastStore.getState().addToast('error', t('chat.toast.ai_error'), data.detail || t('chat.toast.ai_error_unknown'));
            }
          } catch {
            // Ignore parse errors on incomplete lines
          }
        }
      }

      flushUpdate();

      // Latency fallback when no token was emitted (e.g. proposals straight away).
      if (assistantMessage.latencyMs === undefined) {
        assistantMessage.latencyMs = Math.round(performance.now() - sendStartTs);
        updateAssistantMessage();
      }
    } catch (err) {
      console.error('SSE Error:', err);
      wasRateLimited = wasRateLimited || (err instanceof Error && err.message === 'HTTP 429');
      // Don't toast on rate-limit — the api() helper already shows a deduped toast for 429s
      if (!wasRateLimited) {
        useToastStore.getState().addToast('error', t('chat.toast.network_error'), t('chat.toast.network_error_disconnected'));
      }
    } finally {
      flushUpdate();
      window.clearTimeout(fetchTimeout);
      set({ isStreaming: false, _abortController: undefined, activeSteps: [], activeTools: [], activeMeta: null });
      // Skip fetchSessions on rate-limit to prevent a 429 cascade
      const state = get();
      if (!wasRateLimited) {
        const nodeIdForFetch = state.activeSession?.node_id || null;
        get().fetchSessions(nodeIdForFetch);
      }
    }
  },

  updateSession: async (sessionId, title, nodeId) => {
    const { sessions } = get();
    const session = sessions.find(s => s.id === sessionId);
    if (!session) return;

    const cleanNodeId = nodeId === 'all' ? null : nodeId;
    const body = {
      id: sessionId,
      title: title,
      node_id: cleanNodeId,
      history: session.history
    };

    try {
      const updated = await api<ChatSession>('/api/chat/sessions', {
        method: 'POST',
        body: JSON.stringify(body)
      });
      if (updated) {
        set(state => {
          const updatedSessions = state.sessions.map(s => s.id === sessionId ? updated : s);
          return {
            sessions: updatedSessions,
            activeSession: state.activeSessionId === sessionId ? updated : state.activeSession,
          };
        });
      }
    } catch {
      useToastStore.getState().addToast('error', t('chat.toast.error'), t('chat.toast.update_error'));
    }
  },

  approveProposal: async (proposalId) => {
    try {
      const res = await api<ActionProposal>(`/api/chat/proposals/${proposalId}/approve`, {
        method: 'POST'
      });
      if (res) {
        if (res.status === 'FAILED') {
          const errorMsg = res.result?.error || t('chat.toast.proposal_execute_error');
          useToastStore.getState().addToast('error', t('chat.toast.failure'), String(errorMsg));
          return false;
        }
        useToastStore.getState().addToast('success', t('chat.toast.success'), t('chat.toast.proposal_approved'));
        return true;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('chat.toast.proposal_execute_error');
      useToastStore.getState().addToast('error', t('chat.toast.failure'), message);
    }
    return false;
  },

  rejectProposal: async (proposalId, reason) => {
    try {
      const res = await api<ProposalActionResponse>(`/api/chat/proposals/${proposalId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason || '' })
      });
      if (res) {
        useToastStore.getState().addToast('info', t('chat.toast.rejected'), t('chat.toast.proposal_rejected'));
        return true;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('chat.toast.proposal_reject_error');
      useToastStore.getState().addToast('error', t('chat.toast.failure'), message);
    }
    return false;
  },

  fetchSuggestions: async (nodeId) => {
    try {
      const url = nodeId && nodeId !== 'all'
        ? `/api/chat/suggestions?node_id=${nodeId}`
        : '/api/chat/suggestions';
      const data = await api<string[]>(url);
      if (data) {
        set({ suggestions: data });
      }
    } catch (err) {
      console.error('Failed to fetch suggestions:', err);
    }
  },

  pendingProposalsCount: () => {
    const { activeSession } = get();
    if (!activeSession?.history) return 0;
    return activeSession.history.filter(
      m => m.role === 'assistant' && m.proposal?.status === 'PENDING'
    ).length;
  }
}));
