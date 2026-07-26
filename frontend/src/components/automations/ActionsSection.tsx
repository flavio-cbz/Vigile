import React from 'react';
import { Server, Plus, Trash2 } from 'lucide-react';
import { t } from '../../i18n';
import { FormRow, Section } from './FormSection';
import type { FormAction } from './RuleFormModal';
import { INTENT_ACTIONS } from './ruleFormTypes';

interface ActionsSectionProps {
  actions: FormAction[];
  onAdd: () => void;
  onRemove: (i: number) => void;
  onUpdate: (i: number, updates: Partial<FormAction>) => void;
}

export function ActionsSection({
  actions,
  onAdd,
  onRemove,
  onUpdate,
}: ActionsSectionProps) {
  return (
    <Section title={t('automations.form.actions')} icon={<Server size={14} className="text-emerald-400" />}>
      {actions.length === 0 && (
        <p className="text-xs text-red-400 italic">{t('automations.form.action_required')}</p>
      )}
      {actions.map((action, i) => (
        <div key={i} className="border border-border rounded-lg p-3 space-y-2 bg-surface-2">
          <div className="flex items-center gap-2">
            <select
              className="form-select flex-1"
              value={action.type}
              onChange={e => onUpdate(i, { type: e.target.value as FormAction['type'] })}
            >
              <option value="send_intent">Envoyer une commande Worker</option>
              <option value="call_webhook">Appeler un Webhook</option>
              <option value="log_message">Enregistrer un message</option>
            </select>
            <button className="icon-btn text-red-400 shrink-0" onClick={() => onRemove(i)}>
              <Trash2 size={14} />
            </button>
          </div>

          {action.type === 'send_intent' && (
            <div className="grid grid-cols-2 gap-2">
              <FormRow label="Action Worker">
                <select
                  className="form-select"
                  value={action.action ?? 'RESTART_SERVICE'}
                  onChange={e => onUpdate(i, { action: e.target.value })}
                >
                  {INTENT_ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </FormRow>
              <FormRow label="Paramètre (optionnel)">
                <input
                  className="form-input"
                  placeholder='Ex: {"service": "nginx"}'
                  onChange={e => {
                    try { onUpdate(i, { params: JSON.parse(e.target.value) }); } catch { /* ignore */ }
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
                  onChange={e => onUpdate(i, { url: e.target.value })}
                  placeholder="https://hooks.example.com/notify"
                />
              </FormRow>
              <FormRow label="Template JSON (optionnel)">
                <input
                  className="form-input font-mono text-xs"
                  value={action.body_template ?? ''}
                  onChange={e => onUpdate(i, { body_template: e.target.value })}
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
                onChange={e => onUpdate(i, { message: e.target.value })}
                placeholder="Alerte CPU élevé détecté..."
              />
            </FormRow>
          )}
        </div>
      ))}
      <button className="btn btn-ghost btn-sm mt-1" onClick={onAdd}>
        <Plus size={12} />
        + {t('automations.form.add_action')}
      </button>
    </Section>
  );
}
