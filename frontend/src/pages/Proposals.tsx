import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useNodeStore } from '../store/nodeStore';
import { useChatStore } from '../store/chatStore';
import { useLocale } from '../i18n';
import { api } from '../hooks/useApi';
import { 
  CheckSquare, 
  Terminal, 
  X, 
  Clock, 
  Server, 
  ChevronDown, 
  ChevronUp, 
  UserCheck, 
  UserX, 
  RefreshCw,
  Search,
  CheckCircle2,
  XCircle,
  Play
} from 'lucide-react';

interface Proposal {
  id: string;
  node_id: string;
  action: string;
  params_json: string;
  reasoning: string;
  risk_level: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'FAILED' | 'EXECUTED';
  created_by: string;
  approved_by: string | null;
  rejected_by: string | null;
  rejection_reason: string | null;
  created_at: number;
  updated_at: number;
  executed_at: number | null;
  result_json: string | null;
}

export const Proposals: React.FC = () => {
  const { accessToken, user } = useAuthStore();
  const { nodes, fetchNodes } = useNodeStore();
  const { approveProposal, rejectProposal } = useChatStore();
  const { t } = useLocale();

  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [expandedProposalId, setExpandedProposalId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Rejection modal state
  const [rejectingProposal, setRejectingProposal] = useState<Proposal | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);

  // Operation processing loading state
  const [processingId, setProcessingId] = useState<string | null>(null);

  const isOperatorOrAdmin = user?.role === 'operator' || user?.role === 'admin';

  const fetchProposals = async () => {
    setIsLoading(true);
    try {
      let url = '/api/chat/proposals';
      if (filterStatus !== 'ALL') {
        url += `?status_filter=${filterStatus}`;
      }
      const data = await api<Proposal[]>(url);
      if (data) {
        setProposals(data);
      }
    } catch (err) {
      console.error('Error fetching proposals', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProposals();
    fetchNodes(); // Make sure node names can be resolved
  }, [filterStatus, accessToken]);

  const handleApprove = async (proposalId: string) => {
    if (processingId) return;
    setProcessingId(proposalId);
    const success = await approveProposal(proposalId);
    if (success) {
      fetchProposals();
    }
    setProcessingId(null);
  };

  const handleRejectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingProposal || isRejecting) return;

    setIsRejecting(true);
    const success = await rejectProposal(rejectingProposal.id, rejectionReason);
    if (success) {
      setRejectingProposal(null);
      setRejectionReason('');
      fetchProposals();
    }
    setIsRejecting(false);
  };

  const getNodeName = (nodeId: string) => {
    const node = nodes.find(n => n.id === nodeId);
    return node ? node.name : `Serveur (${nodeId.substring(0, 8)})`;
  };

  const formatEpoch = (epoch: number) => {
    return new Date(epoch * 1000).toLocaleString('fr-FR');
  };

  const toggleExpand = (id: string) => {
    if (expandedProposalId === id) {
      setExpandedProposalId(null);
    } else {
      setExpandedProposalId(id);
    }
  };

  // Filter local search
  const filteredProposals = proposals.filter(p => {
    const nodeName = getNodeName(p.node_id).toLowerCase();
    const action = p.action.toLowerCase();
    const reasoning = p.reasoning.toLowerCase();
    const query = searchQuery.toLowerCase();
    return nodeName.includes(query) || action.includes(query) || reasoning.includes(query);
  });

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Title Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-lg font-bold text-ink-primary tracking-tight flex items-center gap-2">
            <CheckSquare className="w-5 h-5 text-accent-primary" />
            <span>{t('prop.title')}</span>
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Validez ou rejetez les intentions de commandes suggérées par l'intelligence artificielle (Human-in-the-Loop).
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchProposals()}
            className="btn btn-secondary text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-accent-primary' : ''}`} />
            <span>Actualiser</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row gap-4 justify-between items-start sm:items-center">
        <div className="flex rounded border border-border bg-surface-0 overflow-x-auto w-full sm:w-auto p-0.5">
          {[
            { id: 'ALL', label: 'Toutes' },
            { id: 'PENDING', label: t('prop.status.pending') },
            { id: 'APPROVED', label: t('prop.status.approved') },
            { id: 'EXECUTED', label: t('prop.status.executed') },
            { id: 'REJECTED', label: t('prop.status.rejected') },
            { id: 'FAILED', label: t('prop.status.failed') }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setFilterStatus(tab.id)}
              className={`px-3 py-1.5 rounded text-xs font-bold whitespace-nowrap cursor-pointer transition-colors ${
                filterStatus === tab.id 
                  ? 'bg-accent-subtle text-accent-primary border border-accent-primary/20' 
                  : 'text-ink-muted hover:text-ink-primary hover:bg-surface-2 border border-transparent'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72 shrink-0">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Rechercher une proposition..."
            className="input pl-9 text-xs"
          />
        </div>
      </div>

      {/* Proposals list */}
      {isLoading && proposals.length === 0 ? (
        <div className="card p-20 flex flex-col items-center justify-center">
          <RefreshCw className="w-8 h-8 text-accent-primary animate-spin mb-3" />
          <p className="text-xs text-ink-muted">Chargement des propositions d'actions...</p>
        </div>
      ) : filteredProposals.length === 0 ? (
        <div className="card p-16 text-center">
          <CheckSquare className="w-10 h-10 text-ink-muted mx-auto mb-3" />
          <h3 className="text-sm font-bold text-ink-primary">Aucune proposition trouvée</h3>
          <p className="text-xs text-ink-muted mt-1">
            {searchQuery ? "Ajustez vos mots-clés de recherche." : "Les propositions émises par le Copilot IA s'afficheront ici."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredProposals.map((prop) => {
            const isPending = prop.status === 'PENDING';
            const isApproved = prop.status === 'APPROVED' || prop.status === 'EXECUTED';
            const isRejected = prop.status === 'REJECTED';
            const isFailed = prop.status === 'FAILED';
            const isExpanded = expandedProposalId === prop.id;

            let riskColor = 'text-success border-success/20 bg-success-subtle';
            if (prop.risk_level === 'HIGH') riskColor = 'text-danger border-danger/20 bg-danger-subtle';
            else if (prop.risk_level === 'MEDIUM') riskColor = 'text-warning border-warning/20 bg-warning-subtle';

            return (
              <div 
                key={prop.id}
                className={`card transition-all duration-200 ${
                  isPending ? 'border-accent-primary/30 shadow-[0_0_12px_rgba(99,102,241,0.03)]' : 'border-border'
                } p-5 space-y-4`}
              >
                {/* Header info */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] font-mono text-ink-muted bg-surface-1 px-1.5 py-0.5 rounded border border-border">
                        PROP-{prop.id.substring(0, 8).toUpperCase()}
                      </span>
                      <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${riskColor}`}>
                        {t('prop.risk')} {prop.risk_level}
                      </span>
                      <span className={`inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                        isPending ? 'border-accent-primary bg-accent-subtle text-accent-primary' :
                        isApproved ? 'border-success/30 bg-success-subtle text-success' :
                        isRejected ? 'border-border bg-surface-1 text-ink-muted' :
                        'border-danger/30 bg-danger-subtle text-danger'
                      }`}>
                        {prop.status}
                      </span>
                    </div>

                    <div className="flex items-center gap-4 text-[10px] text-ink-muted mt-1.5">
                      <span className="flex items-center gap-1 text-ink-secondary">
                        <Server className="w-3.5 h-3.5" />
                        <span>{getNodeName(prop.node_id)}</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" />
                        <span>Émise le {formatEpoch(prop.created_at)}</span>
                      </span>
                    </div>
                  </div>

                  {/* Actions buttons or status actors */}
                  <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-auto">
                    {isPending && isOperatorOrAdmin ? (
                      <>
                        <button
                          onClick={() => setRejectingProposal(prop)}
                          disabled={processingId !== null}
                          className="btn btn-danger py-1 px-3 text-xs"
                        >
                          {t('prop.btn.reject')}
                        </button>
                        <button
                          onClick={() => handleApprove(prop.id)}
                          disabled={processingId !== null}
                          className="btn btn-primary py-1 px-3.5 text-xs flex items-center gap-1"
                        >
                          {processingId === prop.id ? (
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <>
                              <Play className="w-3.5 h-3.5" />
                              <span>{t('prop.btn.approve')}</span>
                            </>
                          )}
                        </button>
                      </>
                    ) : (
                      <div className="text-[10px] text-ink-muted space-y-0.5 text-right font-medium">
                        {prop.approved_by && (
                          <div className="flex items-center gap-1 justify-end text-success">
                            <UserCheck className="w-3 h-3" />
                            <span>Approuvée par {prop.approved_by}</span>
                          </div>
                        )}
                        {prop.rejected_by && (
                          <div className="flex items-center gap-1 justify-end text-ink-muted">
                            <UserX className="w-3 h-3 text-danger" />
                            <span>Rejetée par {prop.rejected_by}</span>
                          </div>
                        )}
                        {prop.executed_at && (
                          <div className="text-[9px] opacity-75">
                            Exécutée le {formatEpoch(prop.executed_at)}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Reasoning section */}
                <div className="p-3.5 rounded bg-surface-1 border border-border/50 text-xs text-ink-secondary italic leading-relaxed">
                  <strong>{t('prop.reasoning')} :</strong> {prop.reasoning}
                </div>

                {/* Command text preview box */}
                <div className="space-y-1.5">
                  <div className="text-[10px] font-bold text-ink-muted uppercase tracking-wider flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5 text-accent-primary" />
                    <span>{t('prop.action')}</span>
                  </div>
                  <div className="p-3 rounded bg-[#06060a] border border-border font-mono text-xs text-success/90 overflow-x-auto whitespace-pre-wrap select-all">
                    {prop.action}
                  </div>
                </div>

                {/* Rejection reason details */}
                {prop.rejection_reason && (
                  <div className="p-3 bg-danger-subtle border border-danger/20 rounded text-xs text-danger leading-normal">
                    <strong>Motif du rejet :</strong> {prop.rejection_reason}
                  </div>
                )}

                {/* Collapsible execution reports (result_json) */}
                {prop.result_json && (
                  <div className="border-t border-border/60 pt-3">
                    <button
                      onClick={() => toggleExpand(prop.id)}
                      className="flex items-center gap-1.5 text-xs text-accent-primary hover:underline cursor-pointer select-none font-bold"
                    >
                      {isExpanded ? (
                        <>
                          <ChevronUp className="w-4 h-4" />
                          <span>Masquer le rapport d'exécution</span>
                        </>
                      ) : (
                        <>
                          <ChevronDown className="w-4 h-4" />
                          <span>Afficher le rapport d'exécution ({prop.status})</span>
                        </>
                      )}
                    </button>

                    {isExpanded && (
                      <div className="mt-3 space-y-2.5 animate-fade-in">
                        <div className="h-8 border-b border-border bg-[#06060a] px-3.5 flex items-center justify-between text-[9px] text-ink-muted font-bold tracking-wider rounded-t select-none">
                          <span className="flex items-center gap-1.5">
                            {isFailed ? (
                              <XCircle className="w-3 h-3 text-danger" />
                            ) : (
                              <CheckCircle2 className="w-3 h-3 text-success" />
                            )}
                            <span>CONSOLE TERMINAL OUTPUT</span>
                          </span>
                        </div>
                        <pre className="p-4 rounded bg-[#030304] border border-border text-xs font-mono text-success/80 overflow-x-auto whitespace-pre-wrap select-text max-h-64 leading-relaxed">
                          {(() => {
                            try {
                              const parsed = JSON.parse(prop.result_json);
                              if (parsed.output) return parsed.output;
                              if (parsed.error) return `[ERREUR] ${parsed.error}`;
                              return JSON.stringify(parsed, null, 2);
                            } catch (e) {
                              return prop.result_json;
                            }
                          })()}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* MODAL: REJECT REASON INPUT */}
      {rejectingProposal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-in select-none">
          <div className="w-full max-w-md card p-6 shadow-2xl space-y-5 animate-fade-up">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-xs font-bold text-ink-primary uppercase tracking-wider flex items-center gap-1.5">
                <UserX className="w-4 h-4 text-danger" />
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
                  {isRejecting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
                  <span>Confirmer le Rejet</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
