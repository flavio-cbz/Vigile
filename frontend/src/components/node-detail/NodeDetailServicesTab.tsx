import React, { useMemo, useState } from 'react';
import { Search, RefreshCw } from 'lucide-react';
import { Spinner } from '../primitives/Spinner';
import { useLocale } from '../../i18n';
import type { ServiceRecord } from './types';

export const NodeDetailServicesTab: React.FC<{
  services: ServiceRecord[];
  loading: boolean;
  restartingService: string | null;
  isAdmin: boolean;
  isAdminOrOperator: boolean;
  onRefresh: () => void;
  onRestart: (serviceName: string) => void;
}> = ({ services, loading, restartingService, isAdmin, isAdminOrOperator, onRefresh, onRestart }) => {
  const { t } = useLocale();
  const [serviceSearch, setServiceSearch] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');

  const filteredServices = useMemo(() => {
    return services.filter((srv) => {
      const matchesSearch = srv.name.toLowerCase().includes(serviceSearch.toLowerCase());
      const matchesStatus =
        serviceFilter === '' ||
        (serviceFilter === 'running' && srv.state === 'running') ||
        (serviceFilter === 'failed' && srv.state === 'failed') ||
        (serviceFilter === 'other' && srv.state !== 'running' && srv.state !== 'failed');
      return matchesSearch && matchesStatus;
    });
  }, [services, serviceSearch, serviceFilter]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-surface border border-border rounded-lg">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-3" />
          <input
            type="text"
            placeholder={t('node_detail.services_search_placeholder')}
            value={serviceSearch}
            onChange={(e) => setServiceSearch(e.target.value)}
            className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded pl-10 pr-3.5 py-1.5 text-xs text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
          />
        </div>

        <div className="flex items-center gap-2 font-interface text-xs">
          <select
            value={serviceFilter}
            onChange={(e) => setServiceFilter(e.target.value)}
            className="bg-surface-2 border border-border rounded px-3 py-1.5 focus:outline-none text-text-2 font-semibold"
          >
            <option value="">{t('node_detail.services_filter_all')}</option>
            <option value="running">{t('node_detail.services_filter_running')}</option>
            <option value="failed">{t('node_detail.services_filter_failed')}</option>
            <option value="other">{t('node_detail.services_filter_other')}</option>
          </select>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-1.5 rounded hover:bg-surface-2 text-text-2 hover:text-text-1 cursor-pointer transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {loading && services.length === 0 ? (
        <div className="py-20 text-center text-text-3 flex flex-col items-center justify-center gap-2">
          <Spinner size="sm" />
          <span>{t('node_detail.services_loading')}</span>
        </div>
      ) : filteredServices.length === 0 ? (
        <div className="py-12 text-center text-text-3 text-xs bg-surface/20 border border-border rounded-lg">
          {t('node_detail.services_empty')}
        </div>
      ) : (
        <div className="border border-border rounded-xl bg-surface overflow-hidden shadow">
          <table className="w-full text-left border-collapse text-xs font-sans">
            <thead>
              <tr className="bg-surface-2/45 border-b border-border text-[9px] font-extrabold font-interface tracking-widest text-text-3 uppercase">
                <th className="px-5 py-3">{t('node_detail.services_table_name')}</th>
                <th className="px-5 py-3">{t('node_detail.services_table_state')}</th>
                <th className="px-5 py-3">{t('node_detail.services_table_status')}</th>
                {isAdminOrOperator && <th className="px-5 py-3 text-right">{t('node_detail.services_table_control')}</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredServices.map((srv) => (
                <tr key={srv.name} className="hover:bg-surface-2/20">
                  <td className="px-5 py-3.5 font-mono text-[11.5px] text-text-1 font-bold truncate max-w-[280px]" title={srv.name}>
                    {srv.name}
                  </td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold border uppercase tracking-wider font-interface ${
                      srv.state === 'running'
                        ? 'bg-severity-ok/10 text-severity-ok border-severity-ok/20'
                        : srv.state === 'failed'
                        ? 'bg-severity-critical/10 text-severity-critical border-severity-critical/20 animate-pulse'
                        : 'bg-text-3/15 text-text-2 border-border'
                    }`}>
                      {srv.state}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 font-mono text-[10px] text-text-3 truncate max-w-[200px]" title={srv.status}>
                    {srv.status || t('node_detail.services_no_details')}
                  </td>
                  {isAdminOrOperator && (
                    <td className="px-5 py-3.5 text-right font-interface">
                      <button
                        onClick={() => onRestart(srv.name)}
                        disabled={restartingService !== null || !isAdmin}
                        className="px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider border border-border hover:border-accent/40 text-text-2 hover:text-accent hover:bg-accent/5 rounded cursor-pointer disabled:opacity-50 transition-all duration-150"
                        title={isAdmin ? t('node_detail.restart_service_title') : t('node_detail.admin_required')}
                      >
                        {restartingService === srv.name ? t('card.restarting') : t('card.restart')}
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
