import React from 'react';
import { Zap } from 'lucide-react';
import { t } from '../../i18n';
import { FormRow, Section } from './FormSection';

interface TriggerConfigSectionProps {
  triggerType: 'metric_threshold' | 'node_state';
  metric: string;
  operator: string;
  threshold: string;
  nodeState: string;
  onTriggerTypeChange: (v: 'metric_threshold' | 'node_state') => void;
  onMetricChange: (v: string) => void;
  onOperatorChange: (v: string) => void;
  onThresholdChange: (v: string) => void;
  onNodeStateChange: (v: string) => void;
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

export function TriggerConfigSection({
  triggerType,
  metric,
  operator,
  threshold,
  nodeState,
  onTriggerTypeChange,
  onMetricChange,
  onOperatorChange,
  onThresholdChange,
  onNodeStateChange,
}: TriggerConfigSectionProps) {
  return (
    <Section title={t('automations.form.trigger')} icon={<Zap size={14} className="text-amber-400" />}>
      <FormRow label="Type">
        <select
          className="form-select"
          value={triggerType}
          onChange={e => onTriggerTypeChange(e.target.value as 'metric_threshold' | 'node_state')}
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
}
