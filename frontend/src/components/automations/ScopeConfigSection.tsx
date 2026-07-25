import React from 'react';
import { Gauge } from 'lucide-react';
import { t } from '../../i18n';
import { FormRow, Section } from './FormSection';

interface ScopeConfigSectionProps {
  targetNodeId: string;
  targetGroup: string;
  cooldown: number;
  nodes: { id: string; name: string }[];
  onTargetNodeIdChange: (v: string) => void;
  onTargetGroupChange: (v: string) => void;
  onCooldownChange: (v: number) => void;
}

export function ScopeConfigSection({
  targetNodeId,
  targetGroup,
  cooldown,
  nodes,
  onTargetNodeIdChange,
  onTargetGroupChange,
  onCooldownChange,
}: ScopeConfigSectionProps) {
  return (
    <Section title={t('automations.form.scope')} icon={<Gauge size={14} className="text-purple-400" />}>
      <div className="grid grid-cols-2 gap-3">
        <FormRow label={t('automations.form.target_node')}>
          <select
            className="form-select"
            value={targetNodeId}
            onChange={e => onTargetNodeIdChange(e.target.value)}
          >
            <option value="">{t('automations.form.all_nodes')}</option>
            {nodes.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
          </select>
        </FormRow>
        <FormRow label={t('automations.form.target_group')}>
          <input
            className="form-input"
            value={targetGroup}
            onChange={e => onTargetGroupChange(e.target.value)}
            placeholder="Ex: production"
            disabled={!!targetNodeId}
          />
        </FormRow>
        <FormRow label={t('automations.form.cooldown')}>
          <input
            className="form-input"
            type="number"
            min={0}
            max={86400}
            value={cooldown}
            onChange={e => onCooldownChange(parseInt(e.target.value) || 0)}
          />
        </FormRow>
      </div>
    </Section>
  );
}
