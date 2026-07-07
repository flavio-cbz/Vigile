import React from 'react';
import type { NodeDetailTabId } from './types';

export interface NodeDetailTab {
  id: NodeDetailTabId;
  label: string;
  count?: number;
}

export const NodeDetailTabs: React.FC<{
  tabs: NodeDetailTab[];
  activeTab: NodeDetailTabId;
  onChange: (id: NodeDetailTabId) => void;
}> = ({ tabs, activeTab, onChange }) => {
  return (
    <div className="border-b border-border font-interface select-none shrink-0 flex overflow-x-auto no-scrollbar gap-4">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`py-2 px-1 text-xs font-bold uppercase tracking-wider border-b-2 cursor-pointer transition-all duration-150 ${
            activeTab === tab.id
              ? 'border-accent text-accent font-extrabold'
              : 'border-transparent text-text-2 hover:text-text-1'
          }`}
        >
          <span className="flex items-center gap-1.5">
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className="px-1.5 py-0.5 rounded-full bg-severity-critical text-white text-[8px] font-mono leading-none">
                {tab.count}
              </span>
            )}
          </span>
        </button>
      ))}
    </div>
  );
};
