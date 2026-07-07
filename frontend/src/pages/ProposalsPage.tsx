import React, { useEffect, useState } from 'react';
import { api } from '../hooks/useApi';
import type { ActionProposal } from '../store/uiStore';
import { useNodeStore, type Node } from '../store/nodeStore';
import { usePermission } from '../hooks/usePermission';
import { useChatStore } from '../store/chatStore';
import { usePageTitle } from '../hooks/usePageTitle';
import { StatusDot } from '../components/primitives/StatusDot';
import { EmptyState } from '../components/ui/EmptyState';
import { TimeAgo } from '../components/primitives/TimeAgo';
import { Spinner } from '../components/primitives/Spinner';
import { Check, X, RefreshCw, ChevronDown, Layers } from 'lucide-react';
import { formatDateTime } from '../utils/formatTime';
import { useLocale } from '../i18n';

const ProposalRow: React.FC<{
  prop: ActionProposal;
  node: Node | undefined;
  isOperator: boolean;
  executing: boolean;
  handleRejectInit: (id: string) => void;
  setApprovingId: (id: string) => void;
  getStatusStyles: (status: string) => string;
}> = ({
  prop,
  node,
  isOperator,
  executing,
  handleRejectInit,
  setApprovingId,
  getStatusStyles,
}) => {
  const { t } = useLocale();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`p-5 border border-border rounded-xl bg-surface hover:border-border-strong flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm transition-all duration-200 ${isExpanded ? '!h-auto' : ''}`}
    >
      <div className="space-y-2 min-w-0 flex-1">
        <div className="flex items-center flex-wrap gap-2">
          <span className={`text-[8px] font-extrabold tracking-widest uppercase px-1.5 py-0.5 border rounded ${getStatusStyles(prop.status)}`}>
            {prop.status}
          </span>
          {node && (
            <div className="flex items-center gap-1 text-[10px] font-bold text-text-2 bg-surface-2 px-1.5 py-0.5 border border-border rounded">
              <StatusDot state={node.state} className="mr-0.5" />
              <span>{node.name}</span>
            </div>
          )}
          <span className="text-text-3 text-[10px] font-mono">
            {t('prop.created')} <TimeAgo timestamp={prop.created_at} />
          </span>
        </div>

        <h4 className="font-mono text-xs text-text-1 font-bold truncate">
          {t('prop.action')} : <span className="text-accent">{prop.action}</span>
          {Boolean(prop.params?.target) && (
            <> · {t('prop.target')} : <code className="text-text-2">{String(prop.params!.target)}</code></>
          )}
        </h4>

        <p className="text-text-2 text-xs font-sans leading-relaxed font-normal">
          {isExpanded ? prop.reasoning : (prop.reasoning && prop.reasoning.length > 70 ? `${prop.reasoning.substring(0, 70)}...` : prop.reasoning)}
          {prop.reasoning && prop.reasoning.length > 70 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded(!isExpanded);
              }}
              className="ml-1.5 text-accent hover:text-accent-hover font-bold inline-block cursor-pointer hover:underline text-[10px]"
            >
              {isExpanded ? t('common.less') : t('common.more')}
            </button>
          )}
        </p>

        {Boolean(prop.params?.result) && (
          <div className="p-3 rounded bg-surface-2 border border-border font-mono text-[10px] text-text-2 leading-relaxed max-h-24 overflow-y-auto mt-2">
            Result: {String(prop.params!.result)}
          </div>
        )}
      </div>

      {prop.status === 'PENDING' && isOperator && (
        <div className="flex sm:flex-col gap-2 shrink-0 sm:w-28 font-interface">
          <button
            onClick={() => handleRejectInit(prop.id)}
            disabled={executing}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[9px] font-bold border border-severity-critical/20 hover:border-severity-critical/50 hover:bg-severity-critical/10 text-severity-critical/80 hover:text-severity-critical rounded cursor-pointer disabled:opacity-50 transition-colors"
          >
            <X className="w-3 h-3" />
            <span>{t('prop.btn.reject')}</span>
          </button>
          <button
            onClick={() => setApprovingId(prop.id)}
            disabled={executing}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[9px] font-bold bg-accent hover:bg-accent-hover text-text-1 rounded shadow cursor-pointer disabled:opacity-50 transition-colors"
          >
            <Check className="w-3 h-3" />
            <span>{t('prop.btn.approve')}</span>
          </button>
        </div>
      )}

      {prop.status === 'PENDING' && !isOperator && (
        <div className="text-[10px] text-text-3 italic font-sans shrink-0 sm:w-28 text-center py-2 border border-dashed border-border rounded">
          Droits requis
        </div>
      )}

      {prop.status !== 'PENDING' && (
        <div className="text-[10px] font-bold font-interface shrink-0 sm:w-36 text-right py-2 select-none">
          {prop.status === 'APPROVED' || prop.status === 'EXECUTED' ? (
            <div className="text-severity-ok flex items-center justify-end gap-1">
              <Check className="w-3.5 h-3.5" />
              <span>Exécuté le {formatDateTime(prop.executed_at || prop.updated_at)}</span>
            </div>
          ) : prop.status === 'FAILED' ? (
            <div className="text-severity-critical flex items-center justify-end gap-1">
              <span className="text-xs">⚠</span>
              <span>Échoué le {formatDateTime(prop.executed_at || prop.updated_at)}</span>
            </div>
          ) : (
            <div className="text-text-3 flex items-center justify-end gap-1">
              <X className="w-3.5 h-3.5" />
              <span>Rejeté le {formatDateTime(prop.updated_at)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export const ProposalsPage: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.proposals'));
  const { nodes } = useNodeStore();
  const { can } = usePermission();
  const isOperator = can('approve-action');

  const [proposals, setProposals] = useState<ActionProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [loadingProposalId, setLoadingProposalId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [filterDropdownOpen, setFilterDropdownOpen] = useState(false);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  const statusOptions = [
    { value: 'ALL', label: 'Tous les statuts' },
    { value: 'PENDING', label: 'En attente (PENDING)' },
    { value: 'APPROVED', label: 'Approuvé (APPROVED)' },
    { value: 'REJECTED', label: 'Rejeté (REJECTED)' },
    { value: 'EXECUTED', label: 'Exécuté (EXECUTED)' },
    { value: 'FAILED', label: 'Échoué (FAILED)' },
  ];

  const selectedStatusLabel = statusOptions.find(o => o.value === filterStatus)?.label || 'Tous les statuts';

  const fetchProposals = async () => {
    setLoading(true);
    try {
      const url = filterStatus === 'ALL'
        ? '/api/chat/proposals'
        : `/api/chat/proposals?status=${filterStatus}`;
      const data = await api<ActionProposal[]>(url);
      if (data) setProposals(data);
    } catch (err) {
      console.error('Failed to fetch proposals:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const url = filterStatus === 'ALL'
          ? '/api/chat/proposals'
          : `/api/chat/proposals?status=${filterStatus}`;
        const data = await api<ActionProposal[]>(url);
        if (data) setProposals(data);
      } catch (err) {
        console.error('Failed to fetch proposals:', err);
      } finally {
        setLoading(false);
      }
    })();
  }, [filterStatus]);

  const handleApprove = async (id: string) => {
    setLoadingProposalId(id);
    try {
      const success = await useChatStore.getState().approveProposal(id);
      if (success) {
        await fetchProposals();
      }
    } catch (err) {
      console.error('Failed to approve proposal:', err);
    } finally {
      setLoadingProposalId(null);
    }
  };

  const handleRejectInit = (id: string) => {
    setRejectingId(id);
    setRejectReason('');
  };

  const getStatusStyles = (status: string) => {
    switch (status) {
      case 'APPROVED':
      case 'EXECUTED':
        return 'bg-severity-ok/10 text-severity-ok border-severity-ok/20';
      case 'REJECTED':
        return 'bg-text-3/10 text-text-2 border-border';
      case 'FAILED':
        return 'bg-severity-critical/10 text-severity-critical border-severity-critical/20';
      case 'PENDING':
      default:
        return 'bg-severity-warning/10 text-severity-warning border-severity-warning/20 animate-pulse';
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6 pb-12 animate-fade-in font-interface">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-extrabold tracking-wider uppercase text-text-1">
            {t('prop_page.title')}
          </h1>
          <p className="text-text-3 text-[10px] uppercase font-semibold tracking-wider mt-0.5 font-sans">
            {t('prop_page.subtitle')}
          </p>
        </div>
        <button
          onClick={fetchProposals}
          disabled={loading}
          className="p-1.5 rounded hover:bg-surface-2 text-text-3 hover:text-text-1 cursor-pointer transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg text-xs">
        <div className="flex items-center gap-1.5 relative">
          <span className="text-text-3 font-semibold uppercase tracking-wider text-[10px]">{t('prop_page.status_label')}</span>
          <button
            onClick={() => setFilterDropdownOpen(!filterDropdownOpen)}
            className="bg-surface-2 border border-border rounded px-2.5 py-1 focus:outline-none text-text-2 font-semibold flex items-center gap-1.5 cursor-pointer hover:border-accent/40 transition-colors"
          >
            <span>{selectedStatusLabel}</span>
            <ChevronDown className={`w-3 h-3 transition-transform ${filterDropdownOpen ? 'rotate-180' : ''}`} />
          </button>
          {filterDropdownOpen && (
            <div className="absolute left-0 mt-1 top-full w-56 rounded-lg bg-surface-2/95 backdrop-blur-md border border-border-strong/60 shadow-[0_8px_32px_var(--shadow-dropdown)] py-1.5 z-50 animate-fade-in">
              {statusOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => {
                    setFilterStatus(option.value);
                    setFilterDropdownOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 text-xs hover:bg-surface-3/40 transition-colors cursor-pointer ${
                    filterStatus === option.value ? 'text-accent font-bold bg-accent-muted/10' : 'text-text-2'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <span className="text-[11px] text-text-2 font-mono font-semibold">
          {t('prop_page.count', { count: proposals.length })}
        </span>
      </div>

      {loading && proposals.length === 0 ? (
        <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
          <Spinner size="sm" />
          <span>{t('prop_page.loading')}</span>
        </div>
        ) : proposals.length === 0 ? (
          <EmptyState
            icon={<Layers className="w-12 h-12" />}
            title={t('prop_page.empty_title')}
            description={t('prop_page.empty_description')}
          />
        ) : (
        <div className="space-y-4">
          {proposals.map((prop) => {
            const node = nodes.find((n) => n.id === prop.node_id);
            const executing = loadingProposalId === prop.id;

            return (
              <ProposalRow
                key={prop.id}
                prop={prop}
                node={node}
                isOperator={isOperator}
                executing={executing}
                handleRejectInit={handleRejectInit}
                setApprovingId={setApprovingId}
                getStatusStyles={getStatusStyles}
              />
            );
          })}
        </div>
      )}

      {rejectingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs select-none animate-fade-in">
          <div className="w-full max-w-md p-6 bg-surface border border-border rounded-xl shadow-2xl space-y-4">
            <div>
              <h3 className="text-sm font-bold text-text-1 font-interface uppercase tracking-wider">
                {t('prop_page.reject_title')}
              </h3>
              <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
                {t('prop_page.reject_description')}
              </p>
            </div>

            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder={t('dash.reject_reason_placeholder')}
              className="w-full h-24 bg-surface-2 border border-border focus:border-accent/40 rounded-lg p-3 text-xs text-text-1 placeholder:text-text-3 focus:outline-none resize-none font-sans"
              autoFocus
            />

            <div className="flex justify-end gap-2.5 font-interface text-[10px] font-bold">
              <button
                type="button"
                onClick={() => {
                  setRejectingId(null);
                  setRejectReason('');
                }}
                className="px-4 py-2 border border-border hover:border-border-strong text-text-2 rounded-lg cursor-pointer transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                disabled={!rejectReason.trim()}
                onClick={async () => {
                  const id = rejectingId;
                  const reason = rejectReason;
                  setRejectingId(null);
                  setRejectReason('');
                  setLoadingProposalId(id);
                  try {
                    const success = await useChatStore.getState().rejectProposal(id, reason);
                    if (success) {
                      await fetchProposals();
                    }
                  } catch (err) {
                    console.error('Failed to reject proposal:', err);
                  } finally {
                    setLoadingProposalId(null);
                  }
                }}
                className="px-4 py-2 bg-severity-critical text-text-1 hover:bg-severity-critical/80 rounded-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {t('prop_page.confirm_reject_action')}
              </button>
            </div>
          </div>
        </div>
      )}

      {approvingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs select-none animate-fade-in">
          <div className="w-full max-w-md p-6 bg-surface border border-border rounded-xl shadow-2xl space-y-4">
            <div>
              <h3 className="text-sm font-bold text-text-1 font-interface uppercase tracking-wider">
                {t('prop_page.confirm_approve_title')}
              </h3>
              <p className="text-text-3 text-xs mt-1.5 font-sans">
                {t('prop_page.confirm_approve_message')}
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setApprovingId(null)}
                className="px-4 py-2 border border-border hover:border-border-strong text-text-2 rounded-lg cursor-pointer transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={async () => {
                  const id = approvingId;
                  setApprovingId(null);
                  await handleApprove(id);
                }}
                className="px-4 py-2 bg-accent hover:bg-accent-hover text-text-1 rounded-lg cursor-pointer transition-all shadow"
              >
                {t('prop_page.confirm_approve_action')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
