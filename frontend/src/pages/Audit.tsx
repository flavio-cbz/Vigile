import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useNodeStore } from '../store/nodeStore';
import { useLocale } from '../i18n';
import { api } from '../hooks/useApi';
import { 
  Activity, 
  ShieldCheck, 
  ShieldAlert, 
  Search, 
  ChevronLeft, 
  ChevronRight, 
  RefreshCw, 
  Info,
  User,
  Server,
  KeyRound,
  Eye,
  EyeOff
} from 'lucide-react';

interface AuditEntry {
  id: string;
  sequence: number;
  timestamp: number;
  user_id: string;
  action: string;
  node_id: string | null;
  details: Record<string, any>;
  previous_hash: string;
  entry_hash: string;
}

export const Audit: React.FC = () => {
  const { accessToken } = useAuthStore();
  const { nodes, fetchNodes } = useNodeStore();
  const { t } = useLocale();

  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  
  const [filterAction, setFilterAction] = useState('');
  const [filterNode, setFilterNode] = useState('ALL');
  const [isLoading, setIsLoading] = useState(false);

  // Integrity Check State
  const [integrityChecking, setIntegrityChecking] = useState(false);
  const [integrityResult, setIntegrityResult] = useState<{ valid: boolean; count: number; error?: string } | null>(null);

  // Collapsed details tracker
  const [expandedEntryId, setExpandedEntryId] = useState<string | null>(null);

  const fetchAuditLog = async () => {
    setIsLoading(true);
    try {
      let url = `/api/audit?limit=${limit}&offset=${offset}`;
      if (filterAction.trim()) {
        url += `&action=${encodeURIComponent(filterAction.trim())}`;
      }
      if (filterNode !== 'ALL') {
        url += `&node_id=${encodeURIComponent(filterNode)}`;
      }

      const data = await api<{ entries: AuditEntry[]; total: number }>(url);
      if (data) {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      }
    } catch (err) {
      console.error('Error fetching audit log', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLog();
    fetchNodes();
  }, [limit, offset, filterNode, accessToken]);

  const verifyChain = async () => {
    if (integrityChecking) return;
    setIntegrityChecking(true);
    setIntegrityResult(null);

    try {
      const data = await api<{ valid: boolean; count: number; reason?: string }>('/api/admin/audit-verify');
      if (data) {
        setIntegrityResult({
          valid: data.valid,
          count: data.count,
          error: data.reason
        });
      }
    } catch (err: any) {
      console.error(err);
      setIntegrityResult({
        valid: false,
        count: 0,
        error: err.message || "Erreur de communication réseau."
      });
    } finally {
      setIntegrityChecking(false);
    }
  };

  const getNodeLabel = (nodeId: string | null) => {
    if (!nodeId) return 'Système / Global';
    const node = nodes.find(n => n.id === nodeId);
    return node ? node.name : `Serveur (${nodeId.substring(0, 8)})`;
  };

  const formatTimestamp = (epoch: number) => {
    return new Date(epoch * 1000).toLocaleString('fr-FR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const getActionBadgeStyle = (action: string) => {
    if (action.includes('REVOKE') || action.includes('DELETE')) {
      return 'border-danger/20 bg-danger-subtle text-danger';
    }
    if (action.includes('APPROVE') || action.includes('GENERATE') || action.includes('ENROLL')) {
      return 'border-success/20 bg-success-subtle text-success';
    }
    if (action.includes('REJECT') || action.includes('FAIL')) {
      return 'border-warning/20 bg-warning-subtle text-warning';
    }
    return 'border-border bg-surface-1 text-ink-muted';
  };

  // Pagination page count calculation
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  const handlePrevPage = () => {
    if (offset > 0) {
      setOffset(Math.max(0, offset - limit));
    }
  };

  const handleNextPage = () => {
    if (offset + limit < total) {
      setOffset(offset + limit);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    fetchAuditLog();
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Title & Integrity block */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-lg font-bold text-ink-primary tracking-tight flex items-center gap-2">
            <Activity className="w-5 h-5 text-accent-primary animate-pulse" />
            <span>{t('audit.title')}</span>
          </h1>
          <p className="text-xs text-ink-muted mt-1 font-sans">
            {t('audit.subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={verifyChain}
            disabled={integrityChecking}
            className="btn btn-secondary text-xs flex items-center gap-1.5 shadow-[0_0_8px_rgba(99,102,241,0.05)]"
          >
            {integrityChecking ? (
              <RefreshCw className="w-4 h-4 animate-spin text-accent-primary" />
            ) : (
              <ShieldCheck className="w-4 h-4 text-accent-primary" />
            )}
            <span>Vérifier la chaîne cryptographique</span>
          </button>
          
          <button
            onClick={() => {
              setOffset(0);
              fetchAuditLog();
            }}
            className="btn btn-secondary text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-accent-primary' : ''}`} />
            <span>Actualiser</span>
          </button>
        </div>
      </div>

      {/* Integrity banner result */}
      {integrityResult && (
        <div className={`p-4 rounded border flex items-start gap-3 animate-fade-in ${
          integrityResult.valid 
            ? 'bg-success-subtle border-success/20 text-success' 
            : 'bg-danger-subtle border-danger/20 text-danger'
        }`}>
          {integrityResult.valid ? (
            <>
              <ShieldCheck className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider">{t('audit.verified')}</h3>
                <p className="text-[10px] opacity-90 mt-0.5">
                  L'algorithme de validation a scanné {integrityResult.count} entrées d'audit. Aucun bloc altéré ou manquant détecté. Le registre est sécurisé.
                </p>
              </div>
            </>
          ) : (
            <>
              <ShieldAlert className="w-5 h-5 shrink-0 mt-0.5 text-danger" />
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider">Rupture de chaîne détectée !</h3>
                <p className="text-[10px] opacity-90 mt-0.5">
                  Attention, la validation cryptographique a échoué. Cause : {integrityResult.error || "Hash non valide"}.
                </p>
              </div>
            </>
          )}
        </div>
      )}

      {/* Filter Block */}
      <form onSubmit={handleSearchSubmit} className="card p-4 flex flex-col md:flex-row gap-4 items-end bg-surface-0">
        <div className={`flex-1 grid grid-cols-1 ${nodes.length > 1 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'} gap-4 w-full`}>
          {/* Action Filter */}
          <div className="space-y-1">
            <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Filtrer par Action</label>
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
              <input
                type="text"
                value={filterAction}
                onChange={(e) => setFilterAction(e.target.value)}
                placeholder="ex. GENERATE_JOIN_TOKEN"
                className="input pl-9 text-xs"
              />
            </div>
          </div>

          {/* Node Filter */}
          {nodes.length > 1 && (
            <div className="space-y-1">
              <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Filtrer par Serveur</label>
              <select
                value={filterNode}
                onChange={(e) => setFilterNode(e.target.value)}
                className="select text-xs py-1.5"
              >
                <option value="ALL">Tous les serveurs</option>
                <option value="GLOBAL">Système / Actions globales</option>
                {nodes.map(node => (
                  <option key={node.id} value={node.id}>{node.name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Page Limit selection */}
          <div className="space-y-1">
            <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider">Entrées par page</label>
            <select
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setOffset(0);
              }}
              className="select text-xs py-1.5"
            >
              {[10, 20, 50, 100, 200].map(val => (
                <option key={val} value={val}>{val} entrées</option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="submit"
          className="btn btn-primary h-[34px] w-full md:w-auto text-xs px-5"
        >
          Filtrer
        </button>
      </form>

      {/* Audit Log Table */}
      <div className="card overflow-hidden p-0 border border-border bg-surface-0">
        {isLoading && entries.length === 0 ? (
          <div className="p-20 text-center">
            <RefreshCw className="w-6 h-6 text-accent-primary animate-spin mx-auto mb-2" />
            <span className="text-xs text-ink-muted">Chargement du journal d'audit...</span>
          </div>
        ) : entries.length === 0 ? (
          <div className="p-16 text-center italic text-xs text-ink-muted">
            Aucun événement enregistré ou correspondant à vos filtres.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border bg-surface-1 text-ink-muted text-[10px] uppercase font-bold tracking-wider">
                  <th className="py-3 px-4">{t('audit.sequence') || 'Séquence'}</th>
                  <th className="py-3 px-4">{t('audit.timestamp') || 'Date & Heure'}</th>
                  <th className="py-3 px-4">{t('audit.action') || 'Action'}</th>
                  <th className="py-3 px-4">{t('audit.user') || 'Opérateur'}</th>
                  <th className="py-3 px-4">{t('audit.node') || 'Serveur'}</th>
                  <th className="py-3 px-4">{t('audit.hash') || 'Hash d\'intégrité'}</th>
                  <th className="py-3 px-4 text-right">Détails</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-medium text-ink-secondary">
                {entries.map((entry) => {
                  const isExpanded = expandedEntryId === entry.id;
                  
                  return (
                    <React.Fragment key={entry.id}>
                      <tr className={`hover:bg-surface-1 transition-colors ${isExpanded ? 'bg-surface-1/40' : ''}`}>
                        <td className="py-3 px-4 font-mono font-bold text-accent-primary">
                          #{entry.sequence}
                        </td>
                        <td className="py-3 px-4 text-ink-muted whitespace-nowrap font-mono text-[11px]">
                          {formatTimestamp(entry.timestamp)}
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider ${getActionBadgeStyle(entry.action)}`}>
                            {entry.action}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-ink-primary flex items-center gap-1.5 whitespace-nowrap">
                          <User className="w-3.5 h-3.5 text-ink-muted" />
                          <span>{entry.user_id === 'system' ? 'Automate / IA' : entry.user_id.substring(0, 8)}</span>
                        </td>
                        <td className="py-3 px-4 text-ink-secondary whitespace-nowrap">
                          {entry.node_id ? (
                            <span className="flex items-center gap-1">
                              <Server className="w-3 h-3 text-ink-muted" />
                              <span>{getNodeLabel(entry.node_id)}</span>
                            </span>
                          ) : (
                            <span className="text-[10px] bg-surface-2 px-1.5 py-0.5 rounded border border-border text-ink-muted">Global</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1 font-mono text-[10px] text-ink-muted hover:text-ink-primary transition-colors cursor-help" title={entry.entry_hash}>
                            <KeyRound className="w-3 h-3 text-accent-primary/60" />
                            <span>{entry.entry_hash.substring(0, 8)}...</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => setExpandedEntryId(isExpanded ? null : entry.id)}
                            className="btn btn-secondary p-1 border-border/60 text-ink-muted hover:text-ink-primary"
                            title="Inspecter les détails"
                          >
                            {isExpanded ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                          </button>
                        </td>
                      </tr>

                      {/* Expanded Details JSON Block */}
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} className="p-4 bg-[#06060a] border-t border-border/60">
                            <div className="space-y-3 animate-fade-in text-left">
                              <div className="flex items-center justify-between text-[10px] font-bold text-ink-muted uppercase tracking-wider">
                                <span className="flex items-center gap-1">
                                  <Info className="w-3.5 h-3.5 text-accent-primary" />
                                  <span>Contexte détaillé de l'action</span>
                                </span>
                                <span className="font-mono text-[9px] lowercase">id: {entry.id}</span>
                              </div>

                              <pre className="p-4 bg-[#030304] border border-border rounded font-mono text-[11px] text-success/80 overflow-x-auto select-text leading-relaxed">
                                {JSON.stringify(entry.details, null, 2)}
                              </pre>

                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1.5 text-[9px] font-mono text-ink-muted leading-relaxed">
                                <div>
                                  <span className="block font-bold text-ink-primary uppercase tracking-wider">Hash Précédent (N-1)</span>
                                  <span className="break-all">{entry.previous_hash}</span>
                                </div>
                                <div>
                                  <span className="block font-bold text-ink-primary uppercase tracking-wider font-sans">Signature Actuelle (N)</span>
                                  <span className="break-all">{entry.entry_hash}</span>
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-border/40 pt-4 text-xs font-semibold text-ink-muted">
          <div>
            Affichage de {offset + 1} à {Math.min(offset + limit, total)} sur {total} événements
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={handlePrevPage}
              disabled={offset === 0}
              className="btn btn-secondary p-1.5 disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span>
              Page {currentPage} sur {totalPages}
            </span>
            <button
              onClick={handleNextPage}
              disabled={offset + limit >= total}
              className="btn btn-secondary p-1.5 disabled:opacity-40"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
