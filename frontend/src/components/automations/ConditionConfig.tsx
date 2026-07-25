import React from 'react';
import { Clock, Plus, Trash2 } from 'lucide-react';
import { Section } from './FormSection';
import type { FormCondition, ConditionType } from './ruleFormTypes';

interface ConditionConfigProps {
  conditions: FormCondition[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onUpdate: (index: number, updates: Partial<FormCondition>) => void;
}

export const ConditionConfig: React.FC<ConditionConfigProps> = ({
  conditions, onAdd, onRemove, onUpdate,
}) => {
  return (
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
              onChange={e => onUpdate(i, { type: e.target.value as ConditionType })}
            >
              <option value="always">Toujours</option>
              <option value="time_window">Fenêtre horaire</option>
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
        + Ajouter une condition
      </button>
    </Section>
  );
};
