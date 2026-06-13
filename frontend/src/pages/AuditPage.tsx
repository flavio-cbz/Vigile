import React, { useEffect, useState } from 'react';
import { api } from '../hooks/useApi';
import { HashChip } from '../components/primitives/HashChip';
import { TimeAgo } from '../components/primitives/TimeAgo';
import { Spinner } from '../components/primitives/Spinner';
import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react';
import { usePermission } from '../hooks/usePermission';
import { useToastStore } from '../store/useToastStore';
import { usePageTitle } from '../hooks/usePageTitle';
import { formatActorName } from '../utils/formatActor';
import { useLocale } from '../i18n';
import { formatAuditText } from '../utils/formatAudit';

interface AuditEntry {
  id: number;
  sequence: number;
  timestamp: string;
  user_id: string;
  actor?: string;
  action: string;
  node_id: string | null;
  details: any;
  previous_hash: string;
  entry_hash: string;
}

export const AuditPage: React.FC = () => {
  usePageTitle('Audit');
  const { isAdmin } = usePermission();
  const { t } = useLocale();

  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [limit] = useState(25);
  const [offset, setOffset] = useState(0);

  // Chain verification status
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{
    valid: boolean;
    total_entries: number;
    first_broken_sequence?: number;
    error?: string;
  } | null>(null);

  const fetchAuditLogs = async () => {
    setLoading(true);
    try {
      const data = await api<{ entries: AuditEntry[]; total: number }>(
        `/api/audit?limit=${limit}&offset=${offset}`
      );
      if (data) {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      }
    } catch (err) {
      console.error('Failed to fetch audit logs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLogs();
  }, [offset]);

  const handleVerifyChain = async () => {
    if (!isAdmin) return;
    setVerifying(true);
    setVerifyResult(null);
    try {
      const data = await api<any>('/api/admin/audit-verify');
      if (data) {
        setVerifyResult(data);
        useToastStore.getState().addToast('success', 'Intégrité vérifiée', 'La chaîne de hash est valide');
      }
    } catch (err: any) {
      console.error('Chain verification error:', err);
      setVerifyResult({
        valid: false,
        total_entries: 0,
        error: err.message || "Impossible d'effectuer l'audit d'intégrité.",
      });
      useToastStore.getState().addToast('error', 'Échec de vérification', 'Incohérence détectée dans la chaîne');
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in font-interface">
      {/* Title block */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-extrabold tracking-wider uppercase text-text-1">
            Registre d'Audit Cryptographique
          </h1>
          <p className="text-text-3 text-[10px] uppercase font-semibold tracking-wider mt-0.5 font-sans">
            Grand livre des transactions sécurisé par une chaîne SHA-256
          </p>
        </div>

        {isAdmin ? (
          <button
            onClick={handleVerifyChain}
            disabled={verifying}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold uppercase tracking-wider bg-accent hover:bg-accent-hover text-text-1 rounded shadow cursor-pointer disabled:opacity-50 transition-colors shrink-0"
          >
            {verifying ? (
              <Spinner size="sm" />
            ) : (
              <Shield className="w-4 h-4 text-text-1" />
            )}
            <span>Vérifier l'intégrité</span>
          </button>
        ) : (
          <div className="px-4 py-2 border border-dashed border-border rounded text-[10px] text-text-3 font-normal font-sans italic shrink-0">
            Audit d'intégrité réservé aux administrateurs
          </div>
        )}
      </div>

      {/* Verification Result Banner */}
      {verifyResult && (
        <div className={`p-4 border rounded-xl flex items-start gap-3.5 animate-fade-in font-sans text-xs ${
          verifyResult.valid
            ? 'bg-severity-ok/10 border-severity-ok/20 text-text-2'
            : 'bg-severity-critical/10 border-severity-critical/20 text-severity-critical'
        }`}>
          <div className="shrink-0 mt-0.5">
            {verifyResult.valid ? (
              <ShieldCheck className="w-5 h-5 text-severity-ok" />
            ) : (
              <ShieldAlert className="w-5 h-5 text-severity-critical animate-bounce" />
            )}
          </div>
          <div className="flex-1">
            <h4 className={`font-interface font-bold uppercase tracking-wide ${
              verifyResult.valid ? 'text-severity-ok' : 'text-severity-critical'
            }`}>
              {verifyResult.valid ? 'Chaîne d\'Audit Intègre' : 'Rupture d\'intégrité détectée'}
            </h4>
            <p className="mt-1 leading-relaxed text-[11px] font-normal">
              {verifyResult.valid
                ? `Vérification terminée. Les ${verifyResult.total_entries} blocs enregistrés correspondent exactement à la signature globale SHA-256. Aucune modification frauduleuse n'a été détectée.`
                : `Alerte de sécurité ! La signature SHA-256 s'est rompue. Premier bloc corrompu détecté : séquence #${
                    verifyResult.first_broken_sequence || 'inconnue'
                  }. Raison : ${verifyResult.error || 'Empreinte de base invalide'}.`}
            </p>
          </div>
          <button
            onClick={() => setVerifyResult(null)}
            className="text-[10px] text-text-3 hover:text-text-1 font-bold font-interface uppercase"
          >
            Masquer
          </button>
        </div>
      )}

      {/* Table list container */}
      <div className="space-y-4">
        {loading && entries.length === 0 ? (
          <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
            <Spinner size="sm" />
            <span>INTERROGATION DU GRAND LIVRE D'AUDIT...</span>
          </div>
        ) : entries.length === 0 ? (
          <div className="py-16 text-center text-text-3 border border-dashed border-border rounded-xl bg-surface/25 text-xs font-sans">
            Aucun log d'audit disponible dans le système.
          </div>
        ) : (
          <div className="border border-border rounded-xl bg-surface overflow-hidden shadow">
            <table className="w-full text-left border-collapse text-xs font-sans">
              <thead>
                <tr className="bg-surface-2/45 border-b border-border text-[9px] font-extrabold font-interface tracking-widest text-text-3 uppercase sticky top-0 z-10">
                  <th className="px-5 py-3 w-16">Séquence</th>
                  <th className="px-5 py-3 w-32">Date</th>
                  <th className="px-5 py-3 w-28">Auteur</th>
                  <th className="px-5 py-3 w-40">Action executée</th>
                  <th className="px-5 py-3">Cible et Détails</th>
                  <th className="px-5 py-3 w-44 text-right">Signature Hash SHA-256</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {entries.map((entry) => (
                  <tr key={entry.id} className="even:bg-surface-2/10 hover:bg-surface-2/20">
                    <td className="px-5 py-3.5 font-mono text-text-3 font-semibold">
                      #{entry.sequence}
                    </td>
                    <td className="px-5 py-3.5">
                      <TimeAgo timestamp={entry.timestamp} />
                    </td>
                    <td className="px-5 py-3.5 font-mono text-[10px] text-text-2 font-semibold">
                      {formatActorName(entry.actor || entry.user_id)}
                    </td>
                    <td className="px-5 py-3.5 font-interface text-[11px] font-bold text-accent uppercase tracking-wide">
                      {entry.action.replace('_', ' ')}
                    </td>
                    <td className="px-5 py-3.5 font-normal text-text-2 leading-relaxed">
                      <p
                        className="text-[11px] font-semibold text-text-1 truncate max-w-[280px]"
                        title={typeof entry.details === 'object' ? JSON.stringify(entry.details) : String(entry.details)}
                      >
                        {formatAuditText(entry, t)}
                      </p>
                      {entry.node_id && (
                        <span className="inline-block mt-0.5 text-[8.5px] font-bold tracking-wide uppercase bg-surface-3 px-1.5 py-0 rounded border border-border text-text-3 font-interface">
                          Node: {entry.node_id.substring(0, 8)}…
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right font-interface">
                      <HashChip hash={entry.entry_hash} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Table Pagination */}
        {total > limit && (
          <div className="flex items-center justify-between px-1 text-xs select-none">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="px-3 py-1.5 border border-border rounded bg-surface hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Précédent
            </button>
            <span className="text-text-3 font-semibold">
              Page {Math.floor(offset / limit) + 1} sur {Math.ceil(total / limit)} ({total} entrées)
            </span>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={offset + limit >= total}
              className="px-3 py-1.5 border border-border rounded bg-surface hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Suivant
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
export type { AuditEntry };
