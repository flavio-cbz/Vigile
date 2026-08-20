import React from 'react';
import { Search } from 'lucide-react';

export interface FilterField {
  name: string;
  label: string;
  type: 'search' | 'select';
  options?: { value: string; label: string }[];
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
}

interface FilterPanelProps {
  fields: FilterField[];
}

export const FilterPanel: React.FC<FilterPanelProps> = ({ fields }) => {
  return (
    <div className="flex flex-col md:flex-row gap-4 p-4 rounded-xl bg-surface-2/40 border border-border-strong/30 backdrop-blur-xs">
      <div className="flex flex-wrap gap-4 items-center flex-1">
        {fields.map((field) => (
          <div key={field.name} className="flex items-center gap-2">
            {field.type === 'search' ? (
              <>
                <Search className="w-4 h-4 text-text-3" />
                <input
                  type="text"
                  value={field.value}
                  onChange={(e) => field.onChange(e.target.value)}
                  placeholder={field.placeholder || field.label}
                  className="px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 font-mono focus:outline-none focus:border-accent transition-all duration-150"
                />
              </>
            ) : (
              <>
                <span className="text-xs text-text-3 font-mono uppercase">{field.label}:</span>
                <select
                  value={field.value}
                  onChange={(e) => field.onChange(e.target.value)}
                  className="px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
                >
                  {field.options?.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
