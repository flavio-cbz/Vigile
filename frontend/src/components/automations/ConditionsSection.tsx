import React from 'react';
import { Plus, Trash2, Clock } from 'lucide-react';
import { t } from '../../i18n';
import { Section } from './FormSection';

interface Condition {
  type: 'always' | 'time_window';
  window?: string;
}

interface ConditionsSectionProps {
  conditions: Condition[];
  onAdd: () => void;
  onRemove: (i: number) => void;
  onUpdate: (i: number, updates: Partial<Condition>) => void;
}

export function ConditionsSection({
  conditions,
  onAdd,
  onRemove,
  onUpdate,
}: ConditionsSectionProps) {
  return (
    <Section title={t('automations.form.conditions')} icon={<Clock size={14} className="text-sky-400" />}>
      {conditions.length === 0 && (
        <p className="text-xs text-text-3 italic">{t('automations.form.no_conditions')}</p>
      )}
      {conditions.map((cond, i) => (
        <div key={i} className="flex items-start gap-2">
          <div className="flex-1 grid grid-cols-2 gap-2">
            <select
              className="form-select"
              value={cond.type}
              onChange={e => onUpdate(i, { type: e.target.value as 'always' | 'time_window' })}
            >
              <option value="always">{t('automations.form.always')}</option>
              <option value="time_window">{t('automations.form.time_window')}</option>
            </select>
            {cond.type === 'time_window' && (
              <input
                className="form-input"
                value={cond.window ?? '08:00-20:00'}
                onChange={e => onUpdate(i, { window: e.target.value })}
                placeholder="08:00-20:00"
              />
            )}
          </div>
          <button className="icon-btn text-red-400" onClick={() => onRemove(i)}>
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      <button className="btn btn-ghost btn-sm mt-1" onClick={onAdd}>
        <Plus size={12} />
        + {t('automations.form.add_condition')}
      </button>
    </Section>
  );
}
