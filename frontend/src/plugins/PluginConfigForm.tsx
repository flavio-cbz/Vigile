import React, { useState } from 'react';
import { Save, X, Info } from 'lucide-react';

interface SchemaProperty {
  type: string;
  title: string;
  default?: unknown;
  description?: string;
  enum?: string[];
}

interface PluginConfigFormProps {
  schema: Record<string, SchemaProperty>;
  initialConfig: Record<string, unknown>;
  onSubmit: (config: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
}

export const PluginConfigForm: React.FC<PluginConfigFormProps> = ({
  schema,
  initialConfig,
  onSubmit,
  onCancel,
}) => {
  const [config, setConfig] = useState<Record<string, unknown>>(() => {
    const defaultValues: Record<string, unknown> = {};
    Object.entries(schema).forEach(([key, prop]) => {
      defaultValues[key] = initialConfig[key] !== undefined ? initialConfig[key] : prop.default;
    });
    return defaultValues;
  });
  const [submitting, setSubmitting] = useState(false);

  const handleChange = (key: string, value: string | boolean) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      // Cast integers and numbers if necessary
      const parsedConfig: Record<string, unknown> = {};
      Object.entries(schema).forEach(([key, prop]) => {
        const val = config[key];
        if (prop.type === 'integer') {
          parsedConfig[key] = parseInt(val, 10) || 0;
        } else if (prop.type === 'number') {
          parsedConfig[key] = parseFloat(val) || 0.0;
        } else {
          parsedConfig[key] = val;
        }
      });
      await onSubmit(parsedConfig);
    } catch (err) {
      console.error('Failed to submit plugin configuration:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5 p-5 rounded-xl border border-zinc-800 bg-zinc-900/30 backdrop-blur-xs select-none">
      <div className="border-b border-zinc-800 pb-2">
        <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-text-3">
          Configuration de l'extension
        </h3>
      </div>

      <div className="flex flex-col gap-4">
        {Object.entries(schema).map(([key, prop]) => {
          const value = config[key];

          return (
            <div key={key} className="flex flex-col gap-1.5">
              <label className="text-xs font-mono font-bold text-text-2 uppercase tracking-wide">
                {prop.title || key}
              </label>

              {prop.description && (
                <span className="text-[10px] text-text-3 flex items-start gap-1 bg-zinc-950/20 px-2 py-1 rounded border border-zinc-850">
                  <Info className="w-3 h-3 text-zinc-500 shrink-0 mt-0.5" />
                  {prop.description}
                </span>
              )}

              {prop.enum ? (
                <select
                  value={value || ''}
                  onChange={(e) => handleChange(key, e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150"
                >
                  {prop.enum.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : prop.type === 'boolean' ? (
                <div className="flex items-center gap-3 py-1">
                  <button
                    type="button"
                    onClick={() => handleChange(key, !value)}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      value ? 'bg-orange-500' : 'bg-zinc-800'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        value ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                  <span className="text-xs font-medium text-text-2">
                    {value ? 'Activé' : 'Désactivé'}
                  </span>
                </div>
              ) : prop.type === 'integer' || prop.type === 'number' ? (
                <input
                  type="number"
                  step={prop.type === 'integer' ? '1' : 'any'}
                  value={value !== undefined ? value : ''}
                  onChange={(e) => handleChange(key, e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent font-mono"
                />
              ) : (
                <input
                  type="text"
                  value={value || ''}
                  onChange={(e) => handleChange(key, e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent"
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="flex justify-end gap-3 border-t border-zinc-800 pt-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-transparent hover:bg-surface-2/40 text-text-2 text-xs font-mono font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50"
        >
          <X className="w-3.5 h-3.5" />
          Annuler
        </button>

        <button
          type="submit"
          disabled={submitting}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-xs font-mono font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50"
        >
          <Save className="w-3.5 h-3.5" />
          {submitting ? 'Enregistrement...' : 'Enregistrer'}
        </button>
      </div>
    </form>
  );
};
