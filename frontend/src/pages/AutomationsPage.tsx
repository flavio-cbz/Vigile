import React, { useEffect, useState, useCallback } from 'react';
import { Zap, Plus, Activity, ScrollText, RefreshCw } from 'lucide-react';
import { api } from '../hooks/useApi';
import { usePermission } from '../hooks/usePermission';
import { useToastStore } from '../store/useToastStore';
import { EmptyState } from '../components/ui/EmptyState';
import { Spinner } from '../components/primitives/Spinner';
import { useLocale } from '../i18n';
import { usePageTitle } from '../hooks/usePageTitle';
import { RuleFormModal } from '../components/automations/RuleFormModal';
import { AutomationLogDrawer } from '../components/automations/AutomationLogDrawer';
import { RuleCard, StatCard } from '../components/automations/RuleCard';
import { TestRuleModal } from '../components/automations/TestRuleModal';
import type { AutomationRule } from '../components/automations/RuleCard';

export const AutomationsPage: React.FC = () => {
  const { t } = useLocale();
  usePageTitle(t('page_title.automations'));
  const { isAdmin, isOperator } = usePermission();
  const addToast = useToastStore((s) => s.addToast);

  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingRule, setEditingRule] = useState<AutomationRule | null>(null);
  const [logRule, setLogRule] = useState<AutomationRule | null>(null);
  const [testingRule, setTestingRule] = useState<AutomationRule | null>(null);

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
    fetchRules();
  }, [fetchRules]);

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

  return (
    <div className="page-container">
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
          <button className="btn btn-ghost btn-sm" onClick={fetchRules} title="Rafraîchir">
            <RefreshCw size={14} />
          </button>
          {isAdmin && (
            <button className="btn btn-primary btn-sm" onClick={() => setShowCreateModal(true)}>
              <Plus size={14} />
              {t('automations.new_rule')}
            </button>
          )}
        </div>
      </div>

      {rules.length > 0 && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          <StatCard label="Règles totales" value={rules.length} icon={<Zap size={16} className="text-amber-400" />} />
          <StatCard label="Actives" value={rules.filter(r => r.enabled).length} icon={<Activity size={16} className="text-emerald-400" />} highlight />
          <StatCard label="Exécutions totales" value={rules.reduce((sum, r) => sum + r.total_executions, 0)} icon={<ScrollText size={16} className="text-sky-400" />} />
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : rules.length === 0 ? (
        <EmptyState
          icon={<Zap size={40} className="text-amber-400/60" />}
          title={t('automations.empty')}
          description={t('automations.empty_hint')}
          action={isAdmin ? { label: t('automations.new_rule'), onClick: () => setShowCreateModal(true) } : undefined}
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
              onEdit={setEditingRule}
              onLogs={setLogRule}
              onTest={setTestingRule}
            />
          ))}
        </div>
      )}

      {(showCreateModal || editingRule) && (
        <RuleFormModal
          rule={editingRule}
          onClose={() => { setShowCreateModal(false); setEditingRule(null); }}
          onSaved={() => { setShowCreateModal(false); setEditingRule(null); fetchRules(); }}
        />
      )}

      {logRule && <AutomationLogDrawer rule={logRule} onClose={() => setLogRule(null)} />}

      {testingRule && (
        <TestRuleModal
          rule={testingRule}
          onClose={() => setTestingRule(null)}
          onTested={() => { setTestingRule(null); fetchRules(); }}
        />
      )}
    </div>
  );
};
