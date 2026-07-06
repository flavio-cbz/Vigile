import React, { useState, useRef, useEffect } from 'react';
import { useLocale } from '../../i18n';
import { Bell, AlertTriangle, ShieldCheck } from 'lucide-react';
import { useNodeStore } from '../../store/nodeStore';
import { useUiStore } from '../../store/uiStore';
import { TimeAgo } from '../primitives/TimeAgo';
import { usePolling } from '../../hooks/usePolling';
import { api } from '../../hooks/useApi';
import type { ActionProposal } from '../../store/uiStore';

export const NotifBell: React.FC = () => {
  const { t } = useLocale();
  const { nodes } = useNodeStore();
  const { openCopilot } = useUiStore();

  const [isOpen, setIsOpen] = useState(false);
  const [proposals, setProposals] = useState<ActionProposal[]>([]);
  const popoverRef = useRef<HTMLDivElement>(null);

  const loadProposals = async () => {
    try {
      const data = await api<ActionProposal[]>('/api/chat/proposals?status=PENDING', { skipToast: true });
      if (data) {
        setProposals(data);
      }
    } catch (err) {
      console.error('Failed to fetch pending proposals for notifications:', err);
    }
  };

  usePolling('notif_bell_proposals', loadProposals, 20000);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const offlineNodes = nodes.filter(n => !n.online && n.state !== 'PENDING');

  const count = offlineNodes.length + proposals.length;

  return (
    <div ref={popoverRef} className="relative select-none font-interface">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-md hover:bg-surface-2/60 text-text-2 hover:text-text-1 cursor-pointer transition-colors"
      >
        <Bell className="w-4 h-4 transition-transform duration-200 hover:rotate-12" />
        {count > 0 && (
          <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-severity-critical text-[8px] font-bold text-white ring-2 ring-surface shadow-[0_0_6px_var(--severity-critical)] animate-pulse">
            {count}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 rounded-lg bg-surface-2/95 backdrop-blur-md border border-border-strong/60 shadow-[0_8px_32px_var(--shadow-dropdown)] py-2 z-50 animate-fade-in text-xs">
          <div className="px-4 py-2 flex items-center justify-between border-b border-border-strong/30">
            <span className="font-bold tracking-wider uppercase text-text-3 font-mono text-[10px]">{t('notif.title')}</span>
            {count > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-severity-critical/15 text-severity-critical font-bold">
                {count}
              </span>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-border-strong/20 scrollable-list">
            {offlineNodes.map((node) => (
              <div key={node.id} className="p-3 hover:bg-surface-3/45 flex items-start gap-2.5 transition-colors">
                <AlertTriangle className="w-4 h-4 text-severity-critical shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-text-1 truncate">
                    {t('notif.node_offline_title')}
                  </p>
                  <p className="text-text-2 text-[10px] mt-0.5 leading-relaxed truncate">
                    {t('notif.node_offline_body', { name: node.name })}
                  </p>
                  <div className="mt-1">
                    <TimeAgo timestamp={node.last_heartbeat} />
                  </div>
                </div>
              </div>
            ))}

            {proposals.map((prop) => (
              <div
                key={prop.id}
                onClick={() => {
                  openCopilot({ trigger: 'proposal', proposal: prop, node_id: prop.node_id });
                  setIsOpen(false);
                }}
                className="p-3 hover:bg-surface-3/45 flex items-start gap-2.5 cursor-pointer transition-colors"
              >
                <AlertTriangle className="w-4 h-4 text-severity-warning shrink-0 mt-0.5 animate-pulse" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-text-1 truncate">
                    {t('notif.proposal_pending_title')}
                  </p>
                  <p className="text-text-2 text-[10px] mt-0.5 leading-relaxed line-clamp-2">
                    {t('prop.action')} : <code className="text-accent font-mono text-[9px]">{prop.action}</code>
                    <br />
                    {prop.reasoning}
                  </p>
                  <div className="mt-1">
                    <TimeAgo timestamp={prop.created_at} />
                  </div>
                </div>
              </div>
            ))}

            {count === 0 && (
              <div className="p-8 text-center text-text-3 flex flex-col items-center gap-2">
                <ShieldCheck className="w-8 h-8 text-severity-ok opacity-40" />
                <span className="font-bold tracking-wide uppercase text-[9px] font-mono">{t('notif.all_clear_title')}</span>
                <span className="text-[10px] text-text-3 font-normal max-w-[180px] mx-auto leading-relaxed">
                  {t('notif.all_clear_body')}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
