/**
 * Form field components for the declarative plugin catalog V2.
 *
 * - GroupedRadio: radio group with optional `bind` that SETS TWO fields
 *   (e.g. server selection + its URL field auto-fill). Partie 4 §1 step-2.
 * - ToggleField: toggle switch with optional `link` variant (underlined text button).
 */

import React from 'react';

// ── GroupedRadio ──

export interface RadioOption {
  value: string;
  label: string;
  /** Optional field bindings: selecting this option sets these fields. */
  bind?: Record<string, unknown>;
}

interface GroupedRadioProps {
  name: string;
  options: RadioOption[];
  value: string;
  onChange: (value: string) => void;
  /** Called when an option with `bind` is selected, receiving the bind payload. */
  onFieldBind?: (fields: Record<string, unknown>) => void;
}

export const GroupedRadio: React.FC<GroupedRadioProps> = ({
  name,
  options,
  value,
  onChange,
  onFieldBind,
}) => {
  const handleChange = (option: RadioOption) => {
    onChange(option.value);
    if (option.bind && onFieldBind) {
      onFieldBind(option.bind);
    }
  };

  return (
    <div className="flex flex-col gap-2" role="radiogroup" aria-label={name}>
      {options.map((opt) => {
        const isSelected = opt.value === value;
        return (
          <label
            key={opt.value}
            className={`flex items-center gap-2 p-1.5 rounded cursor-pointer transition-colors text-xs ${
              isSelected
                ? 'bg-orange-500/15 border border-orange-500/40 text-orange-400 font-semibold'
                : 'hover:bg-surface-hover/50 text-text-2 border border-transparent'
            }`}
          >
            <input
              type="radio"
              name={name}
              checked={isSelected}
              onChange={() => handleChange(opt)}
              className="accent-orange-500"
            />
            <span>{opt.label}</span>
          </label>
        );
      })}
    </div>
  );
};

// ── ToggleField ──

interface ToggleFieldProps {
  name: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** 'switch' renders a standard toggle pill; 'link' renders an underlined text button. */
  variant?: 'switch' | 'link';
}

export const ToggleField: React.FC<ToggleFieldProps> = ({
  name: _name,
  label,
  checked,
  onChange,
  variant = 'switch',
}) => {
  if (variant === 'link') {
    return (
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`underline font-mono text-[11px] cursor-pointer text-left transition-colors ${
          checked ? 'text-orange-300' : 'text-orange-400 hover:text-orange-300'
        }`}
      >
        {label}
      </button>
    );
  }

  // Default: switch toggle (PlexAdmin live indicator pattern)
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-mono font-semibold transition-all cursor-pointer ${
        checked
          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
          : 'bg-surface-2 border-border-strong/30 text-text-3 hover:text-text-1'
      }`}
      role="switch"
      aria-checked={checked}
    >
      <span
        className={`w-2 h-2 rounded-full ${checked ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-600'}`}
      />
      <span>{label}</span>
    </button>
  );
};
