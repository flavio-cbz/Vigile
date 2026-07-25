import React, { useEffect, useState } from 'react';
import { api } from '../hooks/useApi';
import type { ActionProposal } from '../store/uiStore';
import { useNodeStore } from '../store/nodeStore';
import { usePermission } from '../hooks/usePermission';
import { useChatStore } from '../store/chatStore';
import { usePageTitle } from '../hooks/usePageTitle';
import { EmptyState } from '../components/ui/EmptyState';
import { Spinner } from '../components/primitives/Spinner';
import { RefreshCw, ChevronDown, Layers } from 'lucide-react';
import { useLocale } from '../i18n';
import { ProposalRow } from '../components/proposals/ProposalRow';

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
