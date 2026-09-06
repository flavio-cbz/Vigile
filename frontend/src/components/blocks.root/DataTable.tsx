import { AlertCircle } from 'lucide-react';
import type { DataTableProps } from './types';

const ALIGN_CLASSES = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
} as const;

export const DataTable = <T extends Record<string, unknown> = Record<string, unknown>>({
  columns,
  data,
  state,
  rowKey = 'id',
  emptyMessage = 'Aucun conteneur trouvé',
  busyMessage = 'Chargement...',
  error,
  onRetry,
  actions,
}: DataTableProps<T>) => {
  if (state === 'idle') return null;

  if (state === 'busy') {
    return (
      <div className="flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-2xl border border-zinc-800/40">
        <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4" />
        <span className="text-zinc-500 text-sm font-mono">{busyMessage}</span>
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6">
        <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
        <h3 className="text-lg font-bold text-zinc-300">Erreur de chargement</h3>
        {error && (
          <p className="text-zinc-500 text-sm max-w-md mt-1">{error}</p>
        )}
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-4 px-4 py-2 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150"
          >
            Réessayer
          </button>
        )}
      </div>
    );
  }

  if (state === 'empty') {
    return (
      <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6">
        <AlertCircle className="w-12 h-12 text-zinc-600 mb-4" />
        <h3 className="text-lg font-bold text-zinc-300">{emptyMessage}</h3>
      </div>
    );
  }

  const hasActions = typeof actions === 'function';

  return (
    <div className="overflow-x-auto rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-border-strong/40 bg-surface-2/30 font-mono text-[10px] text-text-3 uppercase tracking-wider select-none">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-6 py-4 font-bold ${ALIGN_CLASSES[col.align ?? 'left']}`}
              >
                {col.label}
              </th>
            ))}
            {hasActions && (
              <th className="px-6 py-4 font-bold text-right">Actions</th>
            )}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={String(row[rowKey])}
              className="border-b border-border-strong/15 hover:bg-surface-2/20 transition-colors duration-150 text-sm"
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-6 py-4 ${ALIGN_CLASSES[col.align ?? 'left']}`}
                >
                  {col.render ? col.render(row) : String(row[col.key] ?? '')}
                </td>
              ))}
              {hasActions && (
                <td className="px-6 py-4 text-right">
                  <div className="flex justify-end gap-2">
                    {actions(row)}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default DataTable;
