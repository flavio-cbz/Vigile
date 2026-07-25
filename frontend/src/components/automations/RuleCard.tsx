import React from 'react';
import {
  Zap, Clock, ChevronRight, ScrollText, Play, Globe,
  ToggleLeft, ToggleRight, Trash2, AlertTriangle, MessageSquare,
  Gauge, Server,
} from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { clsx } from 'clsx';
import type { AutomationRule } from './automationRuleHelpers';
import { formatDate, formatScope, formatTrigger } from './automationRuleHelpers';

interface StatCardProps {
  label: string;
  value: number;
  icon: React.ReactNode;
  highlight?: boolean;
}

export const StatCard: React.FC<StatCardProps> = ({ label, value, icon, highlight = false }) => (
  <div className={clsx(
    'card p-4 flex items-center gap-3',
    highlight && 'border-emerald-500/20',
  )}>
    <div className="p-2 rounded-lg bg-white/5">
      {icon}
    </div>
    <div>
      <div className="text-2xl font-bold text-text-1">{value}</div>
      <div className="text-xs text-text-3">{label}</div>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

function TriggerBadge({ type }: { type: string }) {
  const isMetric = type === 'metric_threshold';
  return (
    <span className={clsx(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
      isMetric
        ? 'bg-blue-500/15 text-blue-300 border border-blue-500/30'
        : 'bg-purple-500/15 text-purple-300 border border-purple-500/30',
    )}>
      {isMetric ? <Gauge size={10} /> : <Server size={10} />}
      {isMetric ? 'Métrique' : 'État nœud'}
    </span>
  );
}

function StatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <span className={clsx(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
      enabled
        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
        : 'bg-surface-2 text-text-2 border border-border',
    )}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', enabled ? 'bg-emerald-400' : 'bg-text-3')} />
      {enabled ? 'Actif' : 'Désactivé'}
    </span>
  );
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium text-text-2 uppercase tracking-wider mb-2">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function ConditionChip({ condition }: { condition: Record<string, unknown> }) {
  const ctype = condition.type as string;
  if (ctype === 'time_window') {
    return (
      <span className="flex items-center gap-1 text-xs text-text-1">
        <Clock size={10} className="text-sky-400" />
        Fenêtre : {condition.window as string}
      </span>
    );
  }
  return <span className="text-xs text-text-2">{ctype}</span>;
}

function ActionChip({ action }: { action: Record<string, unknown> }) {
  const atype = action.type as string;
  const icons: Record<string, React.ReactNode> = {
    send_intent: <Zap size={10} className="text-amber-400" />,
    call_webhook: <Globe size={10} className="text-blue-400" />,
    log_message: <MessageSquare size={10} className="text-text-3" />,
  };
  const labels: Record<string, string> = {
    send_intent: `Commande : ${action.action}`,
    call_webhook: `Webhook : ${String(action.url ?? '').slice(0, 30)}`,
    log_message: `Log : ${String(action.message ?? '').slice(0, 40)}`,
  };
  return (
    <span className="flex items-center gap-1 text-xs text-text-1">
      {icons[atype] ?? <AlertTriangle size={10} />}
      {labels[atype] ?? atype}
    </span>
  );
}

// ---------------------------------------------------------------------------
// RuleCard
// ---------------------------------------------------------------------------

interface RuleCardProps {
  rule: AutomationRule;
  isAdmin: boolean;
  isOperator: boolean;
  togglingId: string | null;
  deletingId: string | null;
  onToggle: (r: AutomationRule) => void;
  onDelete: (r: AutomationRule) => void;
  onEdit: (r: AutomationRule) => void;
  onLogs: (r: AutomationRule) => void;
  onTest: (r: AutomationRule) => void;
}

export const RuleCard: React.FC<RuleCardProps> = ({
  rule, isAdmin, togglingId, deletingId,
  onToggle, onDelete, onEdit, onLogs, onTest,
}) => {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className={clsx(
      'card border transition-all duration-200',
      rule.enabled ? 'border-border' : 'border-border opacity-70',
    )}>
      <div className="flex items-center gap-4 p-4">
        <button
          className="text-text-3 hover:text-text-1 transition-colors shrink-0"
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronRight
            size={16}
            className={clsx('transition-transform', expanded && 'rotate-90')}
          />
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-text-1 text-sm truncate">{rule.name}</span>
            <TriggerBadge type={rule.trigger_type} />
            <StatusBadge enabled={rule.enabled} />
          </div>
          <div className="flex items-center gap-4 mt-1 flex-wrap">
            <span className="text-xs text-text-2 font-mono">{formatTrigger(rule)}</span>
            <span className="text-xs text-text-3">•</span>
            <span className="text-xs text-text-3">{formatScope(rule)}</span>
            {rule.cooldown_seconds > 0 && (
              <>
                <span className="text-xs text-text-3">•</span>
                <span className="flex items-center gap-1 text-xs text-text-3">
                  <Clock size={10} />
                  {rule.cooldown_seconds}s cooldown
                </span>
              </>
            )}
          </div>
        </div>

        <div className="hidden md:flex flex-col items-end shrink-0">
          <span className="text-sm font-medium text-text-1">{rule.total_executions}</span>
          <span className="text-xs text-text-3">exécutions</span>
        </div>

        <div className="hidden lg:flex flex-col items-end shrink-0 min-w-[100px]">
          <span className="text-xs text-text-2">{formatDate(rule.last_triggered_at)}</span>
          <span className="text-xs text-text-3">dernier run</span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            className="icon-btn icon-btn-sm text-sky-400 hover:text-sky-300"
            title="Historique"
            onClick={() => onLogs(rule)}
          >
            <ScrollText size={14} />
          </button>
          {isAdmin && (
            <>
              <button
                className="icon-btn icon-btn-sm text-amber-400 hover:text-amber-300"
                title="Tester"
                onClick={() => onTest(rule)}
              >
                <Play size={14} />
              </button>
              <button
                className="icon-btn icon-btn-sm text-text-2 hover:text-text-1"
                title="Éditer"
                onClick={() => onEdit(rule)}
              >
                <Globe size={14} />
              </button>
              <button
                className={clsx(
                  'icon-btn icon-btn-sm',
                  rule.enabled ? 'text-emerald-400 hover:text-red-400' : 'text-text-3 hover:text-emerald-400',
                )}
                title={rule.enabled ? 'Désactiver' : 'Activer'}
                onClick={() => onToggle(rule)}
                disabled={togglingId === rule.id}
              >
                {togglingId === rule.id ? (
                  <Spinner size="sm" />
                ) : rule.enabled ? (
                  <ToggleRight size={14} />
                ) : (
                  <ToggleLeft size={14} />
                )}
              </button>
              <button
                className="icon-btn icon-btn-sm text-text-3 hover:text-red-400"
                title="Supprimer"
                onClick={() => onDelete(rule)}
                disabled={deletingId === rule.id}
              >
                {deletingId === rule.id ? <Spinner size="sm" /> : <Trash2 size={14} />}
              </button>
            </>
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border px-4 py-3 grid grid-cols-1 md:grid-cols-3 gap-4 bg-surface-2">
          <DetailSection title="Conditions">
            {rule.conditions.length === 0 ? (
              <span className="text-xs text-text-3">Toujours</span>
            ) : rule.conditions.map((c, i) => (
              <ConditionChip key={i} condition={c} />
            ))}
          </DetailSection>
          <DetailSection title={`${rule.actions.length} Action${rule.actions.length > 1 ? 's' : ''}`}>
            {rule.actions.map((a, i) => (
              <ActionChip key={i} action={a} />
            ))}
          </DetailSection>
          <DetailSection title="Métadonnées">
            <div className="text-xs text-text-3 space-y-1">
              <div>Créée par <span className="text-text-1">{rule.created_by}</span></div>
              <div>Créée le <span className="text-text-1">{formatDate(rule.created_at)}</span></div>
              {rule.description && (
                <div className="text-text-2 italic mt-1">{rule.description}</div>
              )}
            </div>
          </DetailSection>
        </div>
      )}
    </div>
  );
};
