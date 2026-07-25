import React, { useState, useEffect } from 'react';
import { Play } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useToastStore } from '../../store/useToastStore';
import { Spinner } from '../primitives/Spinner';
import type { AutomationRule } from './automationRuleHelpers';

interface TestRulePanelProps {
  rule: AutomationRule | null;
  onTested: () => void;
}

export const TestRulePanel: React.FC<TestRulePanelProps> = ({ rule, onTested }) => {
  const addToast = useToastStore((s) => s.addToast);
  const [testNodeId, setTestNodeId] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  const [nodes, setNodes] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    api<{ id: string; name: string }[]>('/api/nodes').then(d => {
      if (d) setNodes(d);
    });
  }, []);

  const handleTest = async () => {
    if (!testNodeId || !rule) return;
    setTestLoading(true);
    try {
      await api(`/api/admin/automations/${rule.id}/test`, {
        method: 'POST',
        body: JSON.stringify({ node_id: testNodeId }),
      });
      const nodeName = nodes.find(n => n.id === testNodeId)?.name ?? testNodeId;
      addToast('success', 'Succès', `Test lancé sur ${nodeName}`);
      onTested();
    } catch {
      addToast('error', 'Erreur', 'Échec du test');
    } finally {
      setTestLoading(false);
    }
  };

  if (!rule) return null;

  return (
    <div className="border border-border rounded-lg p-4 bg-surface-2 space-y-3">
      <div className="flex items-center gap-2">
        <Play size={16} className="text-amber-400" />
        <h4 className="text-xs font-bold uppercase tracking-wider text-text-1">Tester la règle</h4>
      </div>
      <p className="text-[10px] text-text-3">Choisissez un nœud cible. Le cooldown et les conditions seront ignorés.</p>
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
      <button
        className="btn btn-primary btn-sm w-full"
        onClick={handleTest}
        disabled={!testNodeId || testLoading}
      >
        {testLoading ? <Spinner size="sm" /> : <Play size={14} />}
        Lancer le test
      </button>
    </div>
  );
};
