import React, { useEffect, useState } from 'react';
import { X, ScrollText, CheckCircle, XCircle, Clock, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { Spinner } from '../primitives/Spinner';
import { clsx } from 'clsx';
import type { AutomationRule } from '../../pages/AutomationsPage';

interface AutomationLog {
  id: string;
  rule_id: string;
  node_id: string | null;
  triggered_at: number;
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED' | 'COOLDOWN';
  trigger_data: Record<string, unknown>;
  result: Record<string, unknown>;
}

interface Props {
  rule: AutomationRule;
  onClose: () => void;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; icon: React.ReactNode }> = {
    SUCCESS: { color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30', icon: <CheckCircle size={12} /> },
    FAILED: { color: 'text-red-400 bg-red-500/10 border-red-500/30', icon: <XCircle size={12} /> },
    SKIPPED: { color: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30', icon: <AlertTriangle size={12} /> },
    COOLDOWN: { color: 'text-amber-400 bg-amber-500/10 border-amber-500/30', icon: <Clock size={12} /> },
  };
  const { color, icon } = config[status] ?? config.SKIPPED;
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border', color)}>
      {icon}
      {status}
    </span>
  );
}

function LogRow({ log }: { log: AutomationLog }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-zinc-800/40 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <StatusBadge status={log.status} />
        <span className="text-xs text-zinc-400 flex-1">
          {log.node_id ? (
            <span className="font-mono text-zinc-300">{log.node_id.slice(0, 8)}…</span>
          ) : (
            <span className="text-zinc-500">—</span>
          )}
        </span>
        <span className="text-xs text-zinc-500">{formatDate(log.triggered_at)}</span>
        {expanded ? (
          <ChevronUp size={12} className="text-zinc-500 shrink-0" />
        ) : (
          <ChevronDown size={12} className="text-zinc-500 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-zinc-800 px-4 py-3 bg-zinc-900/30 space-y-2">
          <div>
            <div className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-1">Données de déclenchement</div>
            <pre className="text-xs text-zinc-300 font-mono bg-black/30 rounded p-2 overflow-x-auto">
              {JSON.stringify(log.trigger_data, null, 2)}
            </pre>
          </div>
          {Object.keys(log.result).length > 0 && (
            <div>
              <div className="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-1">Résultat des actions</div>
              <pre className="text-xs text-zinc-300 font-mono bg-black/30 rounded p-2 overflow-x-auto">
                {JSON.stringify(log.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export const AutomationLogDrawer: React.FC<Props> = ({ rule, onClose }) => {
  const [logs, setLogs] = useState<AutomationLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const fetchLogs = async (offset = 0) => {
    setLoading(true);
    try {
      const data = await api<AutomationLog[]>(
        `/api/admin/automations/${rule.id}/logs?limit=${PAGE_SIZE}&offset=${offset}`
      );
      if (data) {
        if (offset === 0) setLogs(data);
        else setLogs(prev => [...prev, ...data]);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs(0);
    setPage(0);
  }, [rule.id]);

  const loadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchLogs(nextPage * PAGE_SIZE);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="fixed right-0 top-0 h-full w-full max-w-lg bg-zinc-900 border-l border-zinc-800 shadow-2xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <ScrollText size={18} className="text-sky-400" />
            <div>
              <h2 className="text-sm font-semibold text-white">Historique d'exécution</h2>
              <p className="text-xs text-zinc-500 truncate max-w-[280px]">{rule.name}</p>
            </div>
          </div>
          <button className="icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Stats strip */}
        <div className="grid grid-cols-3 border-b border-zinc-800">
          {[
            { label: 'Total', value: rule.total_executions, color: 'text-white' },
            {
              label: 'Succès',
              value: logs.filter(l => l.status === 'SUCCESS').length,
              color: 'text-emerald-400',
            },
            {
              label: 'Échecs',
              value: logs.filter(l => l.status === 'FAILED').length,
              color: 'text-red-400',
            },
          ].map(stat => (
            <div key={stat.label} className="px-4 py-3 text-center border-r border-zinc-800 last:border-r-0">
              <div className={clsx('text-xl font-bold', stat.color)}>{stat.value}</div>
              <div className="text-xs text-zinc-500">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Log list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading && logs.length === 0 ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-12 text-zinc-500 text-sm">
              Aucune exécution enregistrée.
            </div>
          ) : (
            <>
              {logs.map(log => (
                <LogRow key={log.id} log={log} />
              ))}
              {logs.length % PAGE_SIZE === 0 && logs.length > 0 && (
                <button
                  className="btn btn-ghost btn-sm w-full mt-2"
                  onClick={loadMore}
                  disabled={loading}
                >
                  {loading ? <Spinner size="sm" /> : 'Charger plus'}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
