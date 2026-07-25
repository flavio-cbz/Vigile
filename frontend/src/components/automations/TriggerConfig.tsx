import React from 'react';
import { Zap } from 'lucide-react';
import { Section, FormRow } from './FormSection';
import { METRICS, OPERATORS, NODE_STATES, type TriggerType } from './ruleFormTypes';

interface TriggerConfigProps {
  triggerType: TriggerType;
  metric: string;
  operator: string;
  threshold: string;
  nodeState: string;
  onTriggerTypeChange: (type: TriggerType) => void;
  onMetricChange: (metric: string) => void;
  onOperatorChange: (operator: string) => void;
  onThresholdChange: (threshold: string) => void;
  onNodeStateChange: (state: string) => void;
}

export const TriggerConfig: React.FC<TriggerConfigProps> = ({
  triggerType, metric, operator, threshold, nodeState,
  onTriggerTypeChange, onMetricChange, onOperatorChange, onThresholdChange, onNodeStateChange,
}) => {
  return (
    <Section title="Déclencheur" icon={<Zap size={14} className="text-amber-400" />}>
      <FormRow label="Type">
        <select
          className="form-select"
          value={triggerType}
          onChange={e => onTriggerTypeChange(e.target.value as TriggerType)}
        >
          <option value="metric_threshold">Seuil de métrique</option>
          <option value="node_state">Changement d'état de nœud</option>
        </select>
      </FormRow>

      {triggerType === 'metric_threshold' && (
        <div className="grid grid-cols-3 gap-3">
          <FormRow label="Métrique">
            <select className="form-select" value={metric} onChange={e => onMetricChange(e.target.value)}>
              {METRICS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </FormRow>
          <FormRow label="Opérateur">
            <select className="form-select" value={operator} onChange={e => onOperatorChange(e.target.value)}>
              {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </FormRow>
          <FormRow label="Seuil">
            <input
              className="form-input"
              type="number"
              value={threshold}
              onChange={e => onThresholdChange(e.target.value)}
              placeholder="90"
            />
          </FormRow>
        </div>
      )}

      {triggerType === 'node_state' && (
        <FormRow label="État cible">
          <select className="form-select" value={nodeState} onChange={e => onNodeStateChange(e.target.value)}>
            {NODE_STATES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </FormRow>
      )}
    </Section>
  );
};
