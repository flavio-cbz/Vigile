import React, { useEffect, useState, useCallback } from 'react';
import {
  Zap, Plus, Play, Trash2, ToggleLeft, ToggleRight,
  ScrollText, ChevronRight, AlertTriangle, Clock, Activity,
  Gauge, Server, Globe, MessageSquare, RefreshCw,
} from 'lucide-react';
import { api } from '../hooks/useApi';
import { usePermission } from '../hooks/usePermission';
import { useToastStore } from '../store/useToastStore';
import { EmptyState } from '../components/ui/EmptyState';
import { Spinner } from '../components/primitives/Spinner';
import { useLocale } from '../i18n';
import { usePageTitle } from '../hooks/usePageTitle';
import { clsx } from 'clsx';
import { RuleFormModal } from '../components/automations/RuleFormModal';
import { AutomationLogDrawer } from '../components/automations/AutomationLogDrawer';

export interface AutomationRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  trigger_type: 'metric_threshold' | 'node_state';
  trigger_config: Record<string, unknown>;
  conditions: Record<string, unknown>[];
  actions: Record<string, unknown>[];
  target_node_id: string | null;
  target_group: string | null;
  cooldown_seconds: number;
  created_by: string;
  created_at: number;
  updated_at: number;
  total_executions: number;
  last_triggered_at: number | null;
}

const METRIC_LABELS: Record<string, string> = {
  cpu_percent: 'CPU %',
  cpu_load_1m: 'Load 1m',
  cpu_load_5m: 'Load 5m',
  cpu_load_15m: 'Load 15m',
  mem_percent: 'Mémoire %',
  disk_percent: 'Disque %',
  uptime_seconds: 'Uptime (s)',
  processes: 'Processus',
};

const OPERATOR_SYMBOLS: Record<string, string> = {
  gt: '>',
  lt: '<',
  gte: '≥',
  lte: '≤',
  eq: '=',
};

function formatTrigger(rule: AutomationRule): string {
  if (rule.trigger_type === 'metric_threshold') {
    const cfg = rule.trigger_config;
    const metric = METRIC_LABELS[cfg.metric as string] ?? String(cfg.metric);
    const op = OPERATOR_SYMBOLS[cfg.operator as string] ?? String(cfg.operator);
    return `${metric} ${op} ${cfg.threshold}`;
  }
  if (rule.trigger_type === 'node_state') {
    return `État : ${rule.trigger_config.state}`;
  }
  return rule.trigger_type;
}

function formatScope(rule: AutomationRule): string {
  if (rule.target_group) return `Groupe : ${rule.target_group}`;
  if (rule.target_node_id) return 'Nœud spécifique';
  return 'Tous les nœuds';
}

function formatDate(ts: number | null): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

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

export const AutomationsPage: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.automations'));
  const { isAdmin, isOperator } = usePermission();
  const addToast = useToastStore((s) => s.addToast);

  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingRule, setEditingRule] = useState<AutomationRule | null>(null);

  // Log drawer state
  const [logRule, setLogRule] = useState<AutomationRule | null>(null);

  // Test modal
  const [testingRule, setTestingRule] = useState<AutomationRule | null>(null);
  const [testNodeId, setTestNodeId] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  const [nodes, setNodes] = useState<{ id: string; name: string }[]>([]);

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<AutomationRule[]>('/api/admin/automations');
      if (data) setRules(data);
    } catch {
      addToast('error', t('automations.toast.load_error_title'), t('automations.toast.load_error'));
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    (async () => {
      try {
        const data = await api<AutomationRule[]>('/api/admin/automations');
        if (data) setRules(data);
      } catch {
        addToast('error', t('automations.toast.load_error_title'), t('automations.toast.load_error'));
      } finally {
        setLoading(false);
      }
    })();
    // Also fetch nodes for test modal
    api<{ id: string; name: string }[]>('/api/nodes').then(d => {
      if (d) setNodes(d);
    });
  }, [addToast]);

  const handleToggle = async (rule: AutomationRule) => {
    setTogglingId(rule.id);
    try {
      await api(`/api/admin/automations/${rule.id}/toggle`, { method: 'POST' });
      addToast('success', t('automations.toast.success'), t('automations.toast.toggle_success', { name: rule.name, action: rule.enabled ? t('automations.action.deactivate') : t('automations.action.activate') }));
      fetchRules();
    } catch {
      addToast('error', t('automations.toast.error'), t('automations.toast.toggle_error'));
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (rule: AutomationRule) => {
    if (!window.confirm(t('automations.toast.delete_confirm', { name: rule.name }))) return;
    setDeletingId(rule.id);
    try {
      await api(`/api/admin/automations/${rule.id}`, { method: 'DELETE' });
      addToast('success', t('automations.toast.success'), t('automations.toast.delete_success', { name: rule.name }));
      fetchRules();
    } catch {
      addToast('error', t('automations.toast.error'), t('automations.toast.delete_error'));
    } finally {
      setDeletingId(null);
    }
  };

  const handleTest = async () => {
    if (!testingRule || !testNodeId) return;
    setTestLoading(true);
    try {
      await api(`/api/admin/automations/${testingRule.id}/test`, {
        method: 'POST',
        body: JSON.stringify({ node_id: testNodeId }),
      });
      const nodeName = nodes.find(n => n.id === testNodeId)?.name ?? testNodeId;
      addToast('success', t('automations.toast.success'), t('automations.toast.test_success', { nodeName }));
      setTestingRule(null);
      setTestNodeId('');
      fetchRules();
    } catch {
      addToast('error', t('automations.toast.error'), t('automations.toast.test_error'));
    } finally {
      setTestLoading(false);
    }
  };

  return (
    <div className="page-container">
      {/* Header */}
      <div className="page-header">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
            <Zap size={22} className="text-amber-400" />
          </div>
          <div>
            <h1 className="page-title">{t('automations.title')}</h1>
            <p className="page-subtitle">{t('automations.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-ghost btn-sm"
            onClick={fetchRules}
            title="Rafraîchir"
          >
            <RefreshCw size={14} />
          </button>
          {isAdmin && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setShowCreateModal(true)}
            >
              <Plus size={14} />
              {t('automations.new_rule')}
            </button>
          )}
        </div>
      </div>

      {/* Stats bar */}
      {rules.length > 0 && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          <StatCard
            label="Règles totales"
            value={rules.length}
            icon={<Zap size={16} className="text-amber-400" />}
          />
          <StatCard
            label="Actives"
            value={rules.filter(r => r.enabled).length}
            icon={<Activity size={16} className="text-emerald-400" />}
            highlight
          />
          <StatCard
            label="Exécutions totales"
            value={rules.reduce((sum, r) => sum + r.total_executions, 0)}
            icon={<ScrollText size={16} className="text-sky-400" />}
          />
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex justify-center py-20">
          <Spinner />
        </div>
      ) : rules.length === 0 ? (
        <EmptyState
          icon={<Zap size={40} className="text-amber-400/60" />}
          title={t('automations.empty')}
          description={t('automations.empty_hint')}
          action={isAdmin ? {
            label: t('automations.new_rule'),
            onClick: () => setShowCreateModal(true)
          } : undefined}
        />
      ) : (
        <div className="space-y-3">
          {rules.map(rule => (
            <RuleCard
              key={rule.id}
              rule={rule}
              isAdmin={isAdmin}
              isOperator={isOperator}
              togglingId={togglingId}
              deletingId={deletingId}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onEdit={(r) => setEditingRule(r)}
              onLogs={(r) => setLogRule(r)}
              onTest={(r) => setTestingRule(r)}
            />
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      {(showCreateModal || editingRule) && (
        <RuleFormModal
          rule={editingRule}
          onClose={() => { setShowCreateModal(false); setEditingRule(null); }}
          onSaved={() => { setShowCreateModal(false); setEditingRule(null); fetchRules(); }}
        />
      )}

      {/* Log Drawer */}
      {logRule && (
        <AutomationLogDrawer
          rule={logRule}
          onClose={() => setLogRule(null)}
        />
      )}

      {/* Test modal */}
      {testingRule && (
        <div className="modal-overlay" onClick={() => setTestingRule(null)}>
          <div className="modal-content max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-4">
              <Play size={18} className="text-amber-400" />
              <h2 className="text-lg font-semibold text-text-1">
                Tester la règle
              </h2>
            </div>
            <p className="text-sm text-text-2 mb-4">
              Choisissez un nœud cible. Le cooldown et les conditions seront ignorés.
            </p>
            <div className="mb-4">
              <label className="form-label">Nœud cible</label>
              <select
                className="form-select w-full"
                value={testNodeId}
                onChange={e => setTestNodeId(e.target.value)}
              >
                <option value="">— Sélectionner —</option>
                {nodes.map(n => (
                  <option key={n.id} value={n.id}>{n.name}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => { setTestingRule(null); setTestNodeId(''); }}
              >
                Annuler
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleTest}
                disabled={!testNodeId || testLoading}
              >
                {testLoading ? <Spinner size="sm" /> : <Play size={14} />}
                Lancer le test
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  label, value, icon, highlight = false,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  highlight?: boolean;
}) {
  return (
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
}

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

function RuleCard({
  rule, isAdmin, togglingId, deletingId,
  onToggle, onDelete, onEdit, onLogs, onTest,
}: RuleCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={clsx(
      'card border transition-all duration-200',
      rule.enabled ? 'border-border' : 'border-border opacity-70',
    )}>
      {/* Main row */}
      <div className="flex items-center gap-4 p-4">
        {/* Expand toggle */}
        <button
          className="text-text-3 hover:text-text-1 transition-colors shrink-0"
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronRight
            size={16}
            className={clsx('transition-transform', expanded && 'rotate-90')}
          />
        </button>

        {/* Rule info */}
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

        {/* Stats */}
        <div className="hidden md:flex flex-col items-end shrink-0">
          <span className="text-sm font-medium text-text-1">{rule.total_executions}</span>
          <span className="text-xs text-text-3">exécutions</span>
        </div>

        {/* Last run */}
        <div className="hidden lg:flex flex-col items-end shrink-0 min-w-[100px]">
          <span className="text-xs text-text-2">{formatDate(rule.last_triggered_at)}</span>
          <span className="text-xs text-text-3">dernier run</span>
        </div>

        {/* Actions */}
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

      {/* Expanded detail */}
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
  return (
    <span className="text-xs text-text-2">{ctype}</span>
  );
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
