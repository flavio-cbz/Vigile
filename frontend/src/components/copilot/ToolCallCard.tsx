import React, { useState } from 'react';
import { Terminal, CheckCircle2, XCircle, Loader2, ChevronDown, ChevronRight, Server, Box, Cpu } from 'lucide-react';
import { ToolCall } from '../../types/chat.types';

interface ToolCallCardProps {
  toolCall: ToolCall;
}

export const ToolCallCard: React.FC<ToolCallCardProps> = ({ toolCall }) => {
  const [isOpen, setIsOpen] = useState(false);
  const { name, arguments: args, status, result } = toolCall;

  // Format arguments key-values for quick preview
  const argsPreview = Object.entries(args)
    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
    .join(', ');

  const getStatusIcon = () => {
    switch (status) {
      case 'executing':
        return <Loader2 className="w-4 h-4 text-accent animate-spin" />;
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-rose-500" />;
      default:
        return <Loader2 className="w-4 h-4 text-text-muted animate-spin" />;
    }
  };

  const getHeaderColor = () => {
    switch (status) {
      case 'executing':
        return 'border-l-accent';
      case 'completed':
        return 'border-l-emerald-500';
      case 'failed':
        return 'border-l-rose-500';
      default:
        return 'border-l-surface-3';
    }
  };

  // Specific visualizers for tool outputs
  const renderResult = () => {
    if (!result) return null;

    if (!result.success) {
      return (
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs rounded font-mono break-all whitespace-pre-wrap">
          {result.error || 'Une erreur inconnue est survenue.'}
        </div>
      );
    }

    const { data } = result;

    if (!data) {
      return <div className="text-xs text-text-muted italic p-2">Aucun résultat renvoyé.</div>;
    }

    // Specific renderer for list_services
    if (name === 'list_services' && Array.isArray(data)) {
      return (
        <div className="overflow-x-auto border border-surface-3/50 rounded max-h-[250px] overflow-y-auto">
          <table className="w-full text-xs text-left font-mono">
            <thead className="bg-surface-3/50 text-text-muted sticky top-0">
              <tr>
                <th className="p-2">Service</th>
                <th className="p-2">État</th>
                <th className="p-2">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-3/30">
              {data.map((srv: any, idx: number) => {
                const isActive = srv.state === 'active';
                const isRunning = srv.status === 'running';
                return (
                  <tr key={idx} className="hover:bg-surface-2/40">
                    <td className="p-2 truncate max-w-[150px]" title={srv.name}>{srv.name}</td>
                    <td className="p-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                        isActive ? 'bg-emerald-500/15 text-emerald-400' : 'bg-surface-3 text-text-muted'
                      }`}>
                        {srv.state}
                      </span>
                    </td>
                    <td className="p-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                        isRunning ? 'text-emerald-400 font-semibold' : 'text-text-muted'
                      }`}>
                        {srv.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      );
    }

    // Specific renderer for list_containers
    if (name === 'list_containers' && Array.isArray(data)) {
      return (
        <div className="overflow-x-auto border border-surface-3/50 rounded max-h-[250px] overflow-y-auto">
          <table className="w-full text-xs text-left font-mono">
            <thead className="bg-surface-3/50 text-text-muted sticky top-0">
              <tr>
                <th className="p-2">Conteneur</th>
                <th className="p-2">Image</th>
                <th className="p-2">État</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-3/30">
              {data.map((c: any, idx: number) => {
                const isRunning = c.state === 'running' || c.state === 'up';
                return (
                  <tr key={idx} className="hover:bg-surface-2/40">
                    <td className="p-2 truncate max-w-[120px]" title={c.name}>{c.name}</td>
                    <td className="p-2 truncate max-w-[120px] text-text-muted" title={c.image}>{c.image}</td>
                    <td className="p-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                        isRunning ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
                      }`}>
                        {c.state}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      );
    }

    // Specific renderer for get_node_metrics
    if (name === 'get_node_metrics' && data.metrics) {
      const m = data.metrics;
      const formatPercent = (val: number | undefined) => val !== undefined ? `${val.toFixed(1)}%` : 'N/A';
      return (
        <div className="p-3 bg-surface-2/50 border border-surface-3/40 rounded space-y-2 text-xs">
          <div className="flex justify-between items-center text-text-muted font-mono">
            <span className="flex items-center gap-1"><Server className="w-3.5 h-3.5" /> Nœud :</span>
            <span className="text-text font-semibold">{data.node_name} ({data.state})</span>
          </div>
          <hr className="border-surface-3/30" />
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-surface-3/30 p-2 rounded flex flex-col items-center">
              <span className="text-[10px] text-text-muted uppercase">CPU</span>
              <span className="font-mono text-sm font-bold text-accent">{formatPercent(m.cpu_percent)}</span>
            </div>
            <div className="bg-surface-3/30 p-2 rounded flex flex-col items-center">
              <span className="text-[10px] text-text-muted uppercase">RAM</span>
              <span className="font-mono text-sm font-bold text-accent">{formatPercent(m.mem_percent)}</span>
            </div>
            <div className="bg-surface-3/30 p-2 rounded flex flex-col items-center">
              <span className="text-[10px] text-text-muted uppercase">Disque</span>
              <span className="font-mono text-sm font-bold text-accent">{formatPercent(m.disk_percent)}</span>
            </div>
          </div>
          {m.uptime_seconds && (
            <div className="text-[10px] text-text-muted text-right font-mono">
              Uptime : {(m.uptime_seconds / 3600).toFixed(0)} heures
            </div>
          )}
        </div>
      );
    }

    // Specific renderer for read_logs
    if (name === 'read_logs' && data.output) {
      return (
        <div className="p-3 bg-surface-3/60 border border-surface-3 rounded font-mono text-[10px] text-text-muted overflow-x-auto max-h-[250px] overflow-y-auto whitespace-pre">
          {data.output}
        </div>
      );
    }

    // Specific renderer for get_service_status
    if (name === 'get_service_status') {
      const active = data.active === 'active';
      const enabled = data.enabled === 'enabled';
      return (
        <div className="p-3 bg-surface-2/50 border border-surface-3/40 rounded space-y-2 text-xs font-mono">
          <div className="flex justify-between">
            <span className="text-text-muted">Service :</span>
            <span className="font-semibold text-text">{data.service}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted">État actif :</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
              active ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
            }`}>{data.active}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted">Démarrage auto :</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] ${
              enabled ? 'text-emerald-400 font-semibold' : 'text-text-muted'
            }`}>{data.enabled}</span>
          </div>
        </div>
      );
    }

    // Specific renderer for get_fleet_overview
    if (name === 'get_fleet_overview' && Array.isArray(data)) {
      return (
        <div className="space-y-1.5 max-h-[250px] overflow-y-auto pr-1">
          {data.map((n: any, idx: number) => (
            <div key={idx} className="p-2 bg-surface-2/40 border border-surface-3/30 rounded flex justify-between items-center text-xs">
              <div className="flex items-center gap-1.5 truncate">
                <Server className="w-3.5 h-3.5 text-text-muted" />
                <span className="font-semibold truncate">{n.name}</span>
                <span className="text-[10px] text-text-muted font-mono">{n.hostname}</span>
              </div>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                n.online ? 'bg-emerald-500/10 text-emerald-400' : 'bg-surface-3 text-text-muted'
              }`}>
                {n.online ? 'En ligne' : 'Hors ligne'}
              </span>
            </div>
          ))}
        </div>
      );
    }

    // Default JSON fallback
    return (
      <pre className="p-3 bg-surface-3/50 rounded text-[10px] font-mono text-text-muted overflow-x-auto max-h-[200px]">
        {JSON.stringify(data, null, 2)}
      </pre>
    );
  };

  return (
    <div className={`my-2 bg-surface-2/15 border-l-3 rounded-r overflow-hidden transition-all ${getHeaderColor()}`}>
      <div 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between p-2.5 cursor-pointer hover:bg-surface-3/20 select-none"
      >
        <div className="flex items-center gap-2">
          {getStatusIcon()}
          <span className="font-mono text-xs font-semibold text-text uppercase">
            {name.replace('propose_', 'PROPOSITION : ')}
          </span>
          {argsPreview && (
            <span className="text-[10px] text-text-muted truncate max-w-[180px] font-mono">
              ({argsPreview})
            </span>
          )}
        </div>
        <div>
          {isOpen ? <ChevronDown className="w-4 h-4 text-text-muted" /> : <ChevronRight className="w-4 h-4 text-text-muted" />}
        </div>
      </div>

      {isOpen && (
        <div className="p-3 bg-surface/5 border-t border-surface-3/30 space-y-2">
          {/* Tool parameters inspection */}
          <div className="text-[10px] text-text-muted font-mono">
            <span className="font-semibold text-text">Arguments :</span>{' '}
            {JSON.stringify(args)}
          </div>
          {/* Execution result visualizer */}
          {result && (
            <div className="space-y-1">
              <span className="text-[10px] font-semibold font-mono text-text">Résultat :</span>
              {renderResult()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
