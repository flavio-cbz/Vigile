import React, { useState, useEffect } from 'react';
import { X, Zap, Gauge } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useToastStore } from '../../store/useToastStore';
import { Spinner } from '../primitives/Spinner';
import { t } from '../../i18n';
import type { AutomationRule } from './RuleCard';
import { Section, FormRow } from './FormSection';
import { TriggerConfig } from './TriggerConfig';
import { ConditionConfig } from './ConditionConfig';
import { ActionConfig } from './ActionConfig';
import type {
  TriggerType, ActionType, ConditionType,
  FormAction, FormCondition,
} from './ruleFormTypes';

interface Props {
  rule: AutomationRule | null;
  onClose: () => void;
  onSaved: () => void;
}

export const RuleFormModal: React.FC<Props> = ({ rule, onClose, onSaved }) => {
  const addToast = useToastStore((s) => s.addToast);
  const isEdit = !!rule;

  const [name, setName] = useState(rule?.name ?? '');
  const [description, setDescription] = useState(rule?.description ?? '');
  const [triggerType, setTriggerType] = useState<TriggerType>(rule?.trigger_type ?? 'metric_threshold');
  const [cooldown, setCooldown] = useState(rule?.cooldown_seconds ?? 300);
  const [targetNodeId, setTargetNodeId] = useState(rule?.target_node_id ?? '');
  const [targetGroup, setTargetGroup] = useState(rule?.target_group ?? '');

  const [metric, setMetric] = useState((rule?.trigger_config?.metric as string) ?? 'cpu_percent');
  const [operator, setOperator] = useState((rule?.trigger_config?.operator as string) ?? 'gt');
  const [threshold, setThreshold] = useState(String(rule?.trigger_config?.threshold ?? '90'));
  const [nodeState, setNodeState] = useState((rule?.trigger_config?.state as string) ?? 'LOST');

  const [conditions, setConditions] = useState<FormCondition[]>(
    (rule?.conditions ?? []).map(c => ({
      type: (c.type as ConditionType) ?? 'always',
      window: c.window as string | undefined,
    }))
  );

  const [actions, setActions] = useState<FormAction[]>(
    (rule?.actions ?? []).map(a => ({
      type: (a.type as ActionType) ?? 'send_intent',
      action: a.action as string | undefined,
      url: a.url as string | undefined,
      body_template: a.body_template as string | undefined,
      message: a.message as string | undefined,
    }))
  );

  const [nodes, setNodes] = useState<{ id: string; name: string }[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<{ id: string; name: string }[]>('/api/nodes').then(d => {
      if (d) setNodes(d);
    });
  }, []);

  const addCondition = () => setConditions([...conditions, { type: 'always' }]);
  const removeCondition = (i: number) => setConditions(conditions.filter((_, idx) => idx !== i));
  const updateCondition = (i: number, updates: Partial<FormCondition>) => {
    setConditions(conditions.map((c, idx) => idx === i ? { ...c, ...updates } : c));
  };

  const addAction = () => setActions([...actions, { type: 'send_intent', action: 'RESTART_SERVICE' }]);
  const removeAction = (i: number) => setActions(actions.filter((_, idx) => idx !== i));
  const updateAction = (i: number, updates: Partial<FormAction>) => {
    setActions(actions.map((a, idx) => idx === i ? { ...a, ...updates } : a));
  };

  const buildPayload = () => {
    const triggerConfig = triggerType === 'metric_threshold'
      ? { metric, operator, threshold: parseFloat(threshold) }
      : { state: nodeState };

    const conditionsPayload = conditions.map(c => {
      if (c.type === 'time_window') return { type: 'time_window', window: c.window || '08:00-20:00' };
      return { type: 'always' };
    });

    const actionsPayload = actions.map(a => {
      if (a.type === 'send_intent') return { type: 'send_intent', action: a.action || '', params: a.params || {} };
      if (a.type === 'call_webhook') return { type: 'call_webhook', url: a.url || '', body_template: a.body_template || '' };
      return { type: 'log_message', message: a.message || '' };
    });

    return {
      name, description, trigger_type: triggerType, trigger_config: triggerConfig,
      conditions: conditionsPayload, actions: actionsPayload,
      target_node_id: targetNodeId || null, target_group: targetGroup || null,
      cooldown_seconds: cooldown,
    };
  };

  const handleSave = async () => {
    if (!name.trim()) {
      addToast('error', t('automations.toast.error'), t('automations.form.name_required'));
      return;
    }
    if (actions.length === 0) {
      addToast('error', t('automations.toast.error'), t('automations.form.action_required'));
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await api(`/api/admin/automations/${rule.id}`, {
          method: 'PATCH',
          body: JSON.stringify(buildPayload()),
        });
        addToast('success', t('automations.toast.success'), t('automations.form.updated'));
      } else {
        await api('/api/admin/automations', {
          method: 'POST',
          body: JSON.stringify(buildPayload()),
        });
        addToast('success', t('automations.toast.success'), t('automations.form.created'));
      }
      onSaved();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('common.error_unknown');
      addToast('error', t('automations.toast.error'), t('automations.form.error', { message }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Zap size={20} className="text-amber-400" />
            <h2 className="text-lg font-semibold text-text-1">
              {isEdit ? 'Éditer la règle' : 'Nouvelle règle d\'automatisation'}
            </h2>
          </div>
          <button className="icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="space-y-6">
          <Section title="Informations générales">
            <FormRow label="Nom *">
              <input
                className="form-input"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Ex: Redémarrer nginx si CPU critique"
              />
            </FormRow>
            <FormRow label="Description">
              <input
                className="form-input"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Description optionnelle..."
              />
            </FormRow>
          </Section>

          <TriggerConfig
            triggerType={triggerType}
            metric={metric}
            operator={operator}
            threshold={threshold}
            nodeState={nodeState}
            onTriggerTypeChange={setTriggerType}
            onMetricChange={setMetric}
            onOperatorChange={setOperator}
            onThresholdChange={setThreshold}
            onNodeStateChange={setNodeState}
          />

          <ConditionConfig
            conditions={conditions}
            onAdd={addCondition}
            onRemove={removeCondition}
            onUpdate={updateCondition}
          />

          <ActionConfig
            actions={actions}
            onAdd={addAction}
            onRemove={removeAction}
            onUpdate={updateAction}
          />

          <Section title="Portée & configuration" icon={<Gauge size={14} className="text-purple-400" />}>
            <div className="grid grid-cols-2 gap-3">
              <FormRow label="Nœud cible (optionnel)">
                <select
                  className="form-select"
                  value={targetNodeId}
                  onChange={e => setTargetNodeId(e.target.value)}
                >
                  <option value="">Tous les nœuds</option>
                  {nodes.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
                </select>
              </FormRow>
              <FormRow label="Groupe cible (optionnel)">
                <input
                  className="form-input"
                  value={targetGroup}
                  onChange={e => setTargetGroup(e.target.value)}
                  placeholder="Ex: production"
                  disabled={!!targetNodeId}
                />
              </FormRow>
              <FormRow label="Cooldown (secondes)">
                <input
                  className="form-input"
                  type="number"
                  min={0}
                  max={86400}
                  value={cooldown}
                  onChange={e => setCooldown(parseInt(e.target.value) || 0)}
                />
              </FormRow>
            </div>
          </Section>
        </div>

        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-border">
          <button className="btn btn-ghost" onClick={onClose}>
            Annuler
          </button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? <Spinner size="sm" /> : null}
            {isEdit ? 'Mettre à jour' : 'Créer la règle'}
          </button>
        </div>
      </div>
    </div>
  );
};
