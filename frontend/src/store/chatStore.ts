import { create } from 'zustand';
import { useAuthStore } from './authStore';
import { useToastStore } from './useToastStore';
import { useLocaleStore } from './localeStore';
import { api } from '../hooks/useApi';

export interface Message {
  role: 'system' | 'user' | 'assistant';
  content: string;
  proposal?: {
    id: string;
    action: string;
    risk_level: string;
    reasoning?: string;
  };
}

export interface ChatSession {
  id: string;
  user_id: string;
  node_id: string | null;
  title: string;
  history: Message[];
  created_at: number;
  updated_at: number;
}

export interface Proposal {
  id: string;
  node_id: string;
  action: string;
  params: Record<string, any>;
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
  fetchSessions: (nodeId?: string | null) => Promise<void>;
  selectSession: (sessionId: string | null) => void;
  createSession: (nodeId?: string | null, title?: string) => Promise<ChatSession | null>;
  deleteSession: (sessionId: string) => Promise<void>;
  sendMessage: (content: string, nodeId?: string | null) => Promise<void>;
  updateSession: (sessionId: string, title: string, nodeId: string | null) => Promise<void>;
  approveProposal: (proposalId: string) => Promise<boolean>;
  rejectProposal: (proposalId: string, reason?: string) => Promise<boolean>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  activeSession: null,
  isLoading: false,
  isStreaming: false,

  fetchSessions: async (nodeId) => {
    set({ isLoading: true });
    try {
      const url = nodeId && nodeId !== 'all' 
        ? `/api/chat/sessions?node_id=${nodeId}`
        : '/api/chat/sessions';
      const data = await api<ChatSession[]>(url);
      if (data) {
        set({ sessions: data });
        // Update activeSession reference if selected
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
    } catch (err) {
      useToastStore.getState().addToast('error', 'Erreur', 'Impossible de créer la session de chat.');
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
        useToastStore.getState().addToast('success', 'Succès', 'Conversation supprimée.');
      }
    } catch (err) {
      useToastStore.getState().addToast('error', 'Erreur', 'Impossible de supprimer la conversation.');
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
    const initialHistory = [...(currentSession.history || []), userMessage];
    
    set(state => {
      if (!state.activeSession) return {};
      const updatedSession = { ...state.activeSession, history: initialHistory };
      return {
        isStreaming: true,
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
      history: initialHistory.slice(0, -1) // send everything except the last optimistic user message
    };

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'Accept-Language': locale
        },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('ReadableStream non disponible');
      }

      // Add empty placeholder assistant message
      const assistantMessage: Message = { role: 'assistant', content: '' };
      let updatedHistory = [...initialHistory, assistantMessage];

      set(state => {
        if (!state.activeSession) return {};
        const updatedSession = { ...state.activeSession, history: updatedHistory };
        return {
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
        
        // Save the last incomplete line back to the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;

          try {
            const rawJson = trimmed.substring(5).trim();
            if (!rawJson) continue;
            const data = JSON.parse(rawJson);

            if (data.type === 'token') {
              assistantMessage.content += data.content;
              set(state => {
                if (!state.activeSession) return {};
                const updatedSession = { 
                  ...state.activeSession, 
                  history: [...initialHistory, { ...assistantMessage }] 
                };
                return {
                  activeSession: updatedSession,
                  sessions: state.sessions.map(s => s.id === updatedSession.id ? updatedSession : s)
                };
              });
            } else if (data.type === 'proposal') {
              assistantMessage.proposal = {
                id: data.proposal_id,
                action: data.action,
                risk_level: data.risk_level,
                reasoning: data.reasoning
              };
              set(state => {
                if (!state.activeSession) return {};
                const updatedSession = { 
                  ...state.activeSession, 
                  history: [...initialHistory, { ...assistantMessage }] 
                };
                return {
                  activeSession: updatedSession,
                  sessions: state.sessions.map(s => s.id === updatedSession.id ? updatedSession : s)
                };
              });
            } else if (data.type === 'error') {
              useToastStore.getState().addToast('error', 'Erreur IA', data.detail || 'Erreur inconnue');
            }
          } catch (e) {
            // Ignore parse errors on incomplete lines
          }
        }
      }
    } catch (err) {
      console.error('SSE Error:', err);
      useToastStore.getState().addToast('error', 'Erreur Réseau', 'La connexion IA a été interrompue.');
    } finally {
      set({ isStreaming: false });
      // Fetch latest sessions to sync titles and history
      get().fetchSessions(currentSession.node_id);
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
    } catch (err) {
      useToastStore.getState().addToast('error', 'Erreur', 'Impossible de mettre à jour la conversation.');
    }
  },

  approveProposal: async (proposalId) => {
    try {
      const res = await api<any>(`/api/chat/proposals/${proposalId}/approve`, {
        method: 'POST'
      });
      if (res) {
        useToastStore.getState().addToast('success', 'Succès', 'Proposition approuvée et exécutée avec succès.');
        return true;
      }
    } catch (err: any) {
      useToastStore.getState().addToast('error', 'Échec', err.message || 'Impossible d\'approuver la proposition.');
    }
    return false;
  },

  rejectProposal: async (proposalId, reason) => {
    try {
      const res = await api<any>(`/api/chat/proposals/${proposalId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason || '' })
      });
      if (res) {
        useToastStore.getState().addToast('info', 'Refusé', 'Proposition rejetée.');
        return true;
      }
    } catch (err: any) {
      useToastStore.getState().addToast('error', 'Échec', err.message || 'Impossible de rejeter la proposition.');
    }
    return false;
  }
}));
