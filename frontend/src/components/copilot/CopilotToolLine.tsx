import React, { useState } from 'react';
import type { ToolResult } from '../../store/chatStore';
import { useNodeStore } from '../../store/nodeStore';
import { Check, X, ChevronRight } from 'lucide-react';

interface CopilotToolLineProps {
  tool: ToolResult;
}

const formatDuration = (ms?: number): string => {
  if (ms === undefined) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

export const CopilotToolLine: React.FC<CopilotToolLineProps> = ({ tool }) => {
  const [expanded, setExpanded] = useState(false);
  const { nodes } = useNodeStore();
  const node = tool.nodeId ? nodes.find((n) => n.id === tool.nodeId) : null;
  const nodeLabel = node?.name || (tool.nodeId ? tool.nodeId.substring(0, 8) : '—');
  const isError = !tool.success;
  const duration = formatDuration(tool.durationMs);

  return (
    <div
      className={`cp-tool-line ${isError ? 'is-error' : ''}`}
      role="button"
      tabIndex={0}
      onClick={(e) => {
        e.stopPropagation();
        setExpanded((v) => !v);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          setExpanded((v) => !v);
        }
      }}
      aria-expanded={expanded}
    >
      {isError ? (
        <X className="w-3 h-3 text-severity-critical shrink-0" />
      ) : (
        <Check className="w-3 h-3 text-accent-info-strong shrink-0" />
      )}
      <span className="cp-tool-name">{tool.tool}</span>
      <span className="text-text-3">@</span>
      <span className="text-text-2 truncate">{nodeLabel}</span>
      {duration && (
        <span className="text-text-3 ml-auto shrink-0 tabular-nums">{duration}</span>
      )}
      {tool.proposalId && (
        <span className="text-accent-info-strong text-[9px] uppercase tracking-wider shrink-0">
          proposal
        </span>
      )}
      <ChevronRight
        className={`w-3 h-3 text-text-3 shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`}
      />
    </div>
  );
};
