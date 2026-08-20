import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface NodeOption {
  id: string;
  name: string;
  online: boolean;
}

interface NodeSelectorProps {
  nodes: NodeOption[];
  selected: string;
  onChange: (nodeId: string) => void;
  isLoading?: boolean;
}

const NOEUDS_LABEL = 'Nœuds :';
const EMPTY_TEXT = 'Aucun nœud connecté à votre flotte';
const EMPTY_TEXT_SHORT = 'Aucun nœud connecté';
const LOADING_TEXT = 'Chargement des nœuds...';
const LOADING_SHORT = 'Chargement...';

export const NodeSelector: React.FC<NodeSelectorProps> = ({
  nodes,
  selected,
  onChange,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <span className="text-xs text-text-3 font-mono flex items-center gap-2">
        <RefreshCw className="w-3.5 h-3.5 animate-spin text-orange-400" /> {LOADING_TEXT}
      </span>
    );
  }

  if (nodes.length === 0) {
    return (
      <span className="text-xs text-amber-400 font-mono flex items-center gap-1.5">
        <AlertTriangle className="w-3.5 h-3.5" /> {EMPTY_TEXT}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
      <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-text-3 mr-2 shrink-0">
        {NOEUDS_LABEL}
      </span>
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        className="px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
      >
        <option value="all">Tous les serveurs</option>
        {nodes.map((node) => (
          <option key={node.id} value={node.id}>
            {node.name}
          </option>
        ))}
      </select>
    </div>
  );
};

export const NodePills: React.FC<NodeSelectorProps> = ({
  nodes,
  selected,
  onChange,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
        <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-text-3 mr-2 shrink-0">
          {NOEUDS_LABEL}
        </span>
        <span className="text-xs text-text-3 font-mono flex items-center gap-2">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-orange-400" /> {LOADING_SHORT}
        </span>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
        <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-text-3 mr-2 shrink-0">
          {NOEUDS_LABEL}
        </span>
        <span className="text-xs text-amber-400 font-mono flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" /> {EMPTY_TEXT_SHORT}
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
      <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-text-3 mr-2 shrink-0">
        {NOEUDS_LABEL}
      </span>
      {nodes.map((node) => {
        const isSelected = node.id === selected;
        return (
          <button
            key={node.id}
            onClick={() => onChange(node.id)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl border text-xs font-mono font-semibold transition-all cursor-pointer ${
              isSelected
                ? 'bg-orange-500/10 border-orange-500/40 text-orange-400 shadow-[0_0_12px_rgba(249,115,22,0.15)]'
                : 'bg-surface-2/40 border-border-strong/20 text-text-2 hover:bg-surface-hover/80 hover:text-text-1'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                node.online ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)]' : 'bg-zinc-600'
              }`}
            />
            <span>{node.name}</span>
          </button>
        );
      })}
    </div>
  );
};
