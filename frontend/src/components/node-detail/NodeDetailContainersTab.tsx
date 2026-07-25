import React, { useMemo, useState } from 'react';
import { Search, RefreshCw } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { ContainerRecord } from './types';

export const NodeDetailContainersTab: React.FC<{
  containers: ContainerRecord[];
  loading: boolean;
  restartingContainer: string | null;
  isAdmin: boolean;
  isAdminOrOperator: boolean;
  onRefresh: () => void;
  onRestart: (containerId: string) => void;
}> = ({ containers, loading, restartingContainer, isAdmin, isAdminOrOperator, onRefresh, onRestart }) => {
  const { t } = useLocale();
  const [containerSearch, setContainerSearch] = useState('');

  const filteredContainers = useMemo(() => {
    return containers.filter(
      (cnt) =>
        cnt.name.toLowerCase().includes(containerSearch.toLowerCase()) ||
        cnt.image.toLowerCase().includes(containerSearch.toLowerCase())
    );
  }, [containers, containerSearch]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-3" />
          <input
            type="text"
            placeholder={t('node_detail.containers_search_placeholder')}
            value={containerSearch}
            onChange={(e) => setContainerSearch(e.target.value)}
            className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded pl-10 pr-3.5 py-1.5 text-xs text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
          />
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1.5 rounded hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer transition-colors ml-auto font-interface"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && containers.length === 0 ? (
        <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
          <Spinner size="sm" />
          <span>{t('node_detail.containers_loading')}</span>
        </div>
      ) : filteredContainers.length === 0 ? (
        <div className="py-12 text-center text-text-3 text-xs bg-surface/20 border border-border rounded-lg">
          {t('node_detail.containers_empty')}
        </div>
      ) : (
        <div className="border border-border rounded-xl bg-surface overflow-hidden shadow">
          <table className="w-full text-left border-collapse text-xs font-sans">
            <thead>
              <tr className="bg-surface-2/45 border-b border-border text-[9px] font-extrabold font-interface tracking-widest text-text-3 uppercase">
                <th className="px-5 py-3">{t('node_detail.containers_table_name')}</th>
                <th className="px-5 py-3">{t('node_detail.containers_table_image')}</th>
                <th className="px-5 py-3">{t('node_detail.containers_table_status')}</th>
                <th className="px-5 py-3">{t('node_detail.containers_table_ports')}</th>
                {isAdminOrOperator && <th className="px-5 py-3 text-right">{t('node_detail.containers_table_control')}</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredContainers.map((cnt) => (
                <tr key={cnt.id} className="hover:bg-surface-2/20">
                  <td className="px-5 py-3.5 font-interface text-xs text-text-1 font-bold truncate max-w-[160px]" title={cnt.name}>
                    {cnt.name}
                  </td>
                  <td className="px-5 py-3.5 font-mono text-[10px] text-text-3 truncate max-w-[200px]" title={cnt.image}>
                    {cnt.image}
                  </td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold border uppercase tracking-wider font-interface ${
                      cnt.state.toLowerCase() === 'running'
                        ? 'bg-severity-ok/10 text-severity-ok border-severity-ok/20'
                        : 'bg-text-3/15 text-text-2 border-border'
                    }`}>
                      {cnt.state}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 font-mono text-[9.5px] text-text-3 truncate max-w-[160px]" title={Array.isArray(cnt.ports) ? cnt.ports.join(', ') : String(cnt.ports || '')}>
                    {Array.isArray(cnt.ports) ? cnt.ports.join(', ') : (cnt.ports || t('node_detail.containers_no_ports'))}
                  </td>
                  {isAdminOrOperator && (
                    <td className="px-5 py-3.5 text-right font-interface">
                      <button
                        onClick={() => onRestart(cnt.id)}
                        disabled={restartingContainer !== null || !isAdmin}
                        className="px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent hover:bg-accent/5 rounded cursor-pointer disabled:opacity-50 transition-all duration-150"
                        title={isAdmin ? t('node_detail.restart_container_title') : t('node_detail.admin_required')}
                      >
                        {restartingContainer === cnt.id ? t('card.restarting') : t('card.restart')}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
