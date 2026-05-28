import React from 'react';
import { useNavigate } from 'react-router';
import { X, MessageSquareCode, Trash2 } from 'lucide-react';
import { useNodeStore } from '../../store/nodeStore';
import { useAuthStore } from '../../store/authStore';
import { useToastStore } from '../../store/useToastStore';

interface ChatSession {
  id: string;
  user_id: string;
  node_id: string | null;
  title: string;
  history: any[];
  created_at: number;
  updated_at: number;
}

interface AllChatsModalProps {
  chatSessions: ChatSession[];
  onClose: () => void;
  onSessionDeleted: (sessionId: string) => void;
}

export const AllChatsModal: React.FC<AllChatsModalProps> = ({
  chatSessions,
  onClose,
  onSessionDeleted,
}) => {
  const navigate = useNavigate();
  const nodes = useNodeStore((s) => s.nodes);
  const accessToken = useAuthStore((s) => s.accessToken);
  const addToast = useToastStore((s) => s.addToast);

  const getNodeName = (nodeId: string): string => {
    const node = nodes.find((n) => n.id === nodeId);
    return node ? node.name : `Serveur (${nodeId.substring(0, 8)})`;
  };

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Voulez-vous vraiment supprimer cette conversation ?')) return;

    try {
      const res = await fetch(`/api/chat/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (res.ok) {
        onSessionDeleted(sessionId);
      } else {
        addToast('error', 'Erreur', 'Impossible de supprimer la session.');
      }
    } catch {
      addToast('error', 'Erreur', 'Erreur lors de la communication.');
    }
  };

  return (
    <div className="fixed inset-0 bg-bg/85 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-in">
      <div className="w-full max-w-xl glass-panel p-6 rounded-xl border border-border-custom shadow-2xl space-y-4 animate-fade-up relative max-h-[85vh] flex flex-col">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink cursor-pointer p-1 rounded hover:bg-surface-hover z-10"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="shrink-0 border-b border-border-custom/50 pb-3">
          <h3 className="text-sm font-bold text-ink uppercase tracking-wider flex items-center gap-2">
            <MessageSquareCode className="w-4 h-4 text-accent-custom" />
            <span>Historique des conversations</span>
          </h3>
          <p className="text-[0.625rem] text-ink-muted mt-0.5">
            Consultez et gérez l'intégralité de vos sessions de chat sauvegardées.
          </p>
        </div>

        <div className="flex-grow overflow-y-auto space-y-2 pr-1 scrollbar-thin">
          {chatSessions.length === 0 ? (
            <p className="text-xs text-ink-muted italic py-8 text-center">
              Aucune conversation enregistrée.
            </p>
          ) : (
            chatSessions.map((session) => (
              <div
                key={session.id}
                onClick={() => {
                  navigate(`/chat/${session.id}`);
                  onClose();
                }}
                className="glass-panel hover:glass-panel-strong p-3.5 rounded-lg border border-border-custom hover:border-accent-border/30 transition-all duration-150 flex items-center justify-between cursor-pointer group"
              >
                <div className="min-w-0 pr-4">
                  <div className="text-xs font-bold text-ink group-hover:text-accent-custom transition-colors truncate">
                    {session.title}
                  </div>
                  <div className="flex items-center gap-2 text-[0.5rem] text-ink-muted uppercase tracking-wider font-semibold mt-1">
                    <span className="bg-surface border border-border-strong px-1.5 py-0.2 rounded">
                      {session.node_id ? getNodeName(session.node_id) : 'Global'}
                    </span>
                    <span>
                      Mis à jour :{' '}
                      {new Date(session.updated_at * 1000).toLocaleString('fr-FR')}
                    </span>
                  </div>
                </div>

                <button
                  onClick={(e) => handleDeleteSession(session.id, e)}
                  className="p-1.5 rounded hover:bg-red-soft/20 text-ink-muted hover:text-red-custom shrink-0 transition-colors cursor-pointer"
                  title="Supprimer la session"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="shrink-0 pt-3 border-t border-border-custom/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-border-strong text-ink text-[0.6875rem] font-bold cursor-pointer hover:bg-surface-hover"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
};
