import React, { useState, useRef, useEffect } from 'react';
import { useLocale } from '../../i18n';
import { useNavigate } from 'react-router';
import { useNodeStore } from '../../store/nodeStore';
import { StatusDot } from '../primitives/StatusDot';
import { ChevronDown, Server } from 'lucide-react';

export const NodeSelector: React.FC = () => {
  const { nodes, selectedNodeId, selectNode } = useNodeStore();
  const { t } = useLocale();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const activeNode = nodes.find(n => n.id === selectedNodeId);

  return (
    <div ref={dropdownRef} className="relative select-none font-interface">
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="true"
        aria-expanded={isOpen}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-surface/50 border border-border-strong/70 hover:border-accent/50 hover:bg-surface-2/40 text-text-2 hover:text-text-1 text-[11px] cursor-pointer transition-all duration-200"
      >
        <Server className="w-3.5 h-3.5 text-accent opacity-85 transition-transform duration-200 group-hover:scale-105" />
        <span className="font-semibold tracking-wide uppercase font-mono text-[10px]">
          {activeNode ? activeNode.name : t('node_selector.fleet_all')}
        </span>
        {activeNode && <StatusDot state={activeNode.state} className="ml-1" />}
        <ChevronDown className={`w-3.5 h-3.5 opacity-60 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-2 w-56 rounded-lg bg-surface-2/95 backdrop-blur-md border border-border-strong/60 shadow-[0_8px_32px_var(--shadow-dropdown)] py-1.5 z-50 animate-fade-in">
          <button
            onClick={() => {
              selectNode('all');
              navigate('/');
              setIsOpen(false);
            }}
            className={`w-full flex items-center justify-between px-4 py-2.5 text-left text-xs hover:bg-surface-3/40 transition-colors cursor-pointer ${
              selectedNodeId === 'all' ? 'text-accent font-bold bg-accent-muted/10' : 'text-text-2'
            }`}
          >
            <span className="font-medium">{t('node_selector.fleet_label')}</span>
            <span className="text-[9px] opacity-60 font-mono">{t('node_selector.machine_count', { count: nodes.length })}</span>
          </button>

          <div className="h-px bg-border-strong/30 my-1" />

          <div className="max-h-60 overflow-y-auto scrollable-list">
            {nodes.map((node) => (
              <button
                key={node.id}
                onClick={() => {
                  selectNode(node.id);
                  navigate(`/nodes/${node.id}`);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between px-4 py-2.5 text-left text-xs hover:bg-surface-3/40 transition-colors cursor-pointer ${
                  selectedNodeId === node.id ? 'text-accent font-bold bg-accent-muted/10' : 'text-text-2'
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <StatusDot state={node.state} />
                  <span className="truncate font-medium">{node.name}</span>
                </div>
                <span className="text-[9px] opacity-50 font-mono tracking-tighter truncate max-w-[80px]">
                  {node.hostname || t('node_selector.unknown')}
                </span>
              </button>
            ))}
            {nodes.length === 0 && (
              <div className="px-4 py-4 text-center text-text-3 text-xs font-mono">
                {t('node_selector.empty')}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
