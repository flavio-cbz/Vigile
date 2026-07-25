import React, { useState, useEffect } from 'react';
import { Play } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useToastStore } from '../../store/useToastStore';
import { Spinner } from '../primitives/Spinner';
import type { AutomationRule } from './RuleCard';

interface TestRuleModalProps {
  rule: AutomationRule;
  onClose: () => void;
  onTested: () => void;
}

export const TestRuleModal: React.FC<TestRuleModalProps> = ({ rule, onClose, onTested }) => {
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
    if (!testNodeId) return;
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

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-4">
          <Play size={18} className="text-amber-400" />
          <h2 className="text-lg font-semibold text-text-1">
            Tester la règle
          </h2>
        </div>
        <p className="text-sm text-text-2 mb-4">
          Choisissez un nœud cible. Le cooldown et les conditions seront ignorés.
        </p>
        <div className="mb-4">
          <label className="form-label">Nœud cible</label>
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
        </div>
        <div className="flex justify-end gap-2">
          <button
            className="btn btn-ghost btn-sm"
            onClick={onClose}
          >
            Annuler
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleTest}
            disabled={!testNodeId || testLoading}
          >
            {testLoading ? <Spinner size="sm" /> : <Play size={14} />}
            Lancer le test
          </button>
        </div>
      </div>
    </div>
  );
};
