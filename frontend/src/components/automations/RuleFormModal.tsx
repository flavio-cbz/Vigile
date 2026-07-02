import React, { useState, useEffect } from 'react';
import { X, Zap, Server, Plus, Trash2, Clock, Gauge } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useToastStore } from '../../store/useToastStore';
import { Spinner } from '../primitives/Spinner';
import type { AutomationRule } from '../../pages/AutomationsPage';

interface Props {
  rule: AutomationRule | null;
  onClose: () => void;
  onSaved: () => void;
}

const METRICS = [
  { value: 'cpu_percent', label: 'CPU %' },
  { value: 'cpu_load_1m', label: 'Load 1m' },
  { value: 'cpu_load_5m', label: 'Load 5m' },
  { value: 'cpu_load_15m', label: 'Load 15m' },
  { value: 'mem_percent', label: 'Mémoire %' },
  { value: 'disk_percent', label: 'Disque %' },
  { value: 'uptime_seconds', label: 'Uptime (secondes)' },
  { value: 'processes', label: 'Processus' },
];

const OPERATORS = [
  { value: 'gt', label: '> (supérieur)' },
  { value: 'gte', label: '≥ (supérieur ou égal)' },
  { value: 'lt', label: '< (inférieur)' },
  { value: 'lte', label: '≤ (inférieur ou égal)' },
  { value: 'eq', label: '= (égal)' },
];

const NODE_STATES = ['CONNECTED', 'LOST', 'STALE', 'RECONNECTING'];

const INTENT_ACTIONS = [
  'LIST_SERVICES', 'STATUS_SERVICE', 'RESTART_SERVICE',
  'LIST_CONTAINERS', 'RESTART_CONTAINER', 'GET_STATS', 'READ_LOGS',
];

type TriggerType = 'metric_threshold' | 'node_state';
type ActionType = 'send_intent' | 'call_webhook' | 'log_message';
type ConditionType = 'always' | 'time_window';

interface FormAction {
  type: ActionType;
  // send_intent
  action?: string;
  params?: Record<string, string>;
  // call_webhook
  url?: string;
  body_template?: string;
  headers?: Record<string, string>;
  // log_message
  message?: string;
}

interface FormCondition {
  type: ConditionType;
  window?: string;
}

export const RuleFormModal: React.FC<Props> = ({ rule, onClose, onSaved }) => {
  const addToast = useToastStore((s) => s.addToast);
  const isEdit = !!rule;

  // General fields
  const [name, setName] = useState(rule?.name ?? '');
  const [description, setDescription] = useState(rule?.description ?? '');
  const [triggerType, setTriggerType] = useState<TriggerType>(rule?.trigger_type ?? 'metric_threshold');
  const [cooldown, setCooldown] = useState(rule?.cooldown_seconds ?? 300);
  const [targetNodeId, setTargetNodeId] = useState(rule?.target_node_id ?? '');
  const [targetGroup, setTargetGroup] = useState(rule?.target_group ?? '');

  // Trigger config
  const [metric, setMetric] = useState((rule?.trigger_config?.metric as string) ?? 'cpu_percent');
  const [operator, setOperator] = useState((rule?.trigger_config?.operator as string) ?? 'gt');
  const [threshold, setThreshold] = useState(String(rule?.trigger_config?.threshold ?? '90'));
  const [nodeState, setNodeState] = useState((rule?.trigger_config?.state as string) ?? 'LOST');

  // Conditions
  const [conditions, setConditions] = useState<FormCondition[]>(
    (rule?.conditions ?? []).map(c => ({
      type: (c.type as ConditionType) ?? 'always',
      window: c.window as string | undefined,
    }))
  );

  // Actions
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
      name,
      description,
      trigger_type: triggerType,
      trigger_config: triggerConfig,
      conditions: conditionsPayload,
      actions: actionsPayload,
      target_node_id: targetNodeId || null,
      target_group: targetGroup || null,
      cooldown_seconds: cooldown,
    };
  };

  const handleSave = async () => {
    if (!name.trim()) {
      addToast('error', 'Erreur', 'Le nom de la règle est requis.');
      return;
    }
    if (actions.length === 0) {
      addToast('error', 'Erreur', 'Ajoutez au moins une action.');
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await api(`/api/admin/automations/${rule.id}`, {
          method: 'PATCH',
          body: JSON.stringify(buildPayload()),
        });
        addToast('success', 'Succès', 'Règle mise à jour.');
      } else {
        await api('/api/admin/automations', {
          method: 'POST',
          body: JSON.stringify(buildPayload()),
        });
        addToast('success', 'Succès', 'Règle créée avec succès.');
      }
      onSaved();
    } catch (err: unknown) {
      addToast('error', 'Erreur', `Erreur : ${err instanceof Error ? err.message : 'inconnue'}`);
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
        {/* Header */}
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
          {/* Section: General */}
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

          {/* Section: Trigger */}
          <Section title="Déclencheur" icon={<Zap size={14} className="text-amber-400" />}>
            <FormRow label="Type">
              <select
                className="form-select"
                value={triggerType}
                onChange={e => setTriggerType(e.target.value as TriggerType)}
              >
                <option value="metric_threshold">Seuil de métrique</option>
                <option value="node_state">Changement d'état de nœud</option>
              </select>
            </FormRow>

            {triggerType === 'metric_threshold' && (
              <div className="grid grid-cols-3 gap-3">
                <FormRow label="Métrique">
                  <select className="form-select" value={metric} onChange={e => setMetric(e.target.value)}>
                    {METRICS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                  </select>
                </FormRow>
                <FormRow label="Opérateur">
                  <select className="form-select" value={operator} onChange={e => setOperator(e.target.value)}>
                    {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </FormRow>
                <FormRow label="Seuil">
                  <input
                    className="form-input"
                    type="number"
                    value={threshold}
                    onChange={e => setThreshold(e.target.value)}
                    placeholder="90"
                  />
                </FormRow>
              </div>
            )}

            {triggerType === 'node_state' && (
              <FormRow label="État cible">
                <select className="form-select" value={nodeState} onChange={e => setNodeState(e.target.value)}>
                  {NODE_STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </FormRow>
            )}
          </Section>

          {/* Section: Conditions */}
          <Section title="Conditions (optionnel)" icon={<Clock size={14} className="text-sky-400" />}>
            {conditions.length === 0 && (
              <p className="text-xs text-text-3 italic">Sans condition, la règle s'exécute toujours.</p>
            )}
            {conditions.map((cond, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="flex-1 grid grid-cols-2 gap-2">
                  <select
                    className="form-select"
                    value={cond.type}
                    onChange={e => updateCondition(i, { type: e.target.value as ConditionType })}
                  >
                    <option value="always">Toujours</option>
                    <option value="time_window">Fenêtre horaire</option>
                  </select>
                  {cond.type === 'time_window' && (
                    <input
                      className="form-input"
                      value={cond.window ?? '08:00-20:00'}
                      onChange={e => updateCondition(i, { window: e.target.value })}
                      placeholder="08:00-20:00"
                    />
                  )}
                </div>
                <button className="icon-btn text-red-400" onClick={() => removeCondition(i)}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            <button className="btn btn-ghost btn-sm mt-1" onClick={addCondition}>
              <Plus size={12} />
              + Ajouter une condition
            </button>
          </Section>

          {/* Section: Actions */}
          <Section title="Actions *" icon={<Server size={14} className="text-emerald-400" />}>
            {actions.length === 0 && (
              <p className="text-xs text-red-400 italic">Au moins une action est requise.</p>
            )}
            {actions.map((action, i) => (
              <div key={i} className="border border-border rounded-lg p-3 space-y-2 bg-surface-2">
                <div className="flex items-center gap-2">
                  <select
                    className="form-select flex-1"
                    value={action.type}
                    onChange={e => updateAction(i, { type: e.target.value as ActionType })}
                  >
                    <option value="send_intent">Envoyer une commande Worker</option>
                    <option value="call_webhook">Appeler un Webhook</option>
                    <option value="log_message">Enregistrer un message</option>
                  </select>
                  <button className="icon-btn text-red-400 shrink-0" onClick={() => removeAction(i)}>
                    <Trash2 size={14} />
                  </button>
                </div>

                {action.type === 'send_intent' && (
                  <div className="grid grid-cols-2 gap-2">
                    <FormRow label="Action Worker">
                      <select
                        className="form-select"
                        value={action.action ?? 'RESTART_SERVICE'}
                        onChange={e => updateAction(i, { action: e.target.value })}
                      >
                        {INTENT_ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                      </select>
                    </FormRow>
                    <FormRow label="Paramètre (optionnel)">
                      <input
                        className="form-input"
                        placeholder='Ex: {"service": "nginx"}'
                        onChange={e => {
                          try { updateAction(i, { params: JSON.parse(e.target.value) }); } catch { /* ignore */ }
                        }}
                      />
                    </FormRow>
                  </div>
                )}

                {action.type === 'call_webhook' && (
                  <div className="space-y-2">
                    <FormRow label="URL">
                      <input
                        className="form-input"
                        value={action.url ?? ''}
                        onChange={e => updateAction(i, { url: e.target.value })}
                        placeholder="https://hooks.example.com/notify"
                      />
                    </FormRow>
                    <FormRow label="Template JSON (optionnel)">
                      <input
                        className="form-input font-mono text-xs"
                        value={action.body_template ?? ''}
                        onChange={e => updateAction(i, { body_template: e.target.value })}
                        placeholder='{"node": "{node_id}", "data": {trigger_data}}'
                      />
                    </FormRow>
                  </div>
                )}

                {action.type === 'log_message' && (
                  <FormRow label="Message">
                    <input
                      className="form-input"
                      value={action.message ?? ''}
                      onChange={e => updateAction(i, { message: e.target.value })}
                      placeholder="Alerte CPU élevé détecté..."
                    />
                  </FormRow>
                )}
              </div>
            ))}
            <button className="btn btn-ghost btn-sm mt-1" onClick={addAction}>
              <Plus size={12} />
              + Ajouter une action
            </button>
          </Section>

          {/* Section: Scope & Config */}
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

        {/* Footer */}
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

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function Section({
  title, icon, children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-3">
        {icon}
        <h3 className="text-sm font-semibold text-text-1 uppercase tracking-wider">{title}</h3>
      </div>
      <div className="space-y-3">
        {children}
      </div>
    </div>
  );
}

function FormRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="form-label text-xs">{label}</label>
      {children}
    </div>
  );
}
