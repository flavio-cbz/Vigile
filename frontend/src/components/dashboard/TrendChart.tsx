import React, { useState, useEffect } from 'react';
import { Cpu } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useLocale } from '../../i18n';
import { ChartSkeleton } from '../ui/CardSkeleton';
import type { Node } from '../../store/nodeStore';

interface Snapshot {
  collected_at: number;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
}

interface NodeStatsResponse {
  node_id: string;
  snapshots: Snapshot[];
}

interface TrendChartProps {
  nodes: Node[];
}

interface BarData {
  index: number;
  startTime: number;
  endTime: number;
  status: 'ok' | 'warning' | 'critical' | 'nodata';
  details: string;
  label: string;
  snapshots: Snapshot[];
}

interface IncidentPeriod {
  type: 'critical' | 'warning';
  startTime: number;
  endTime: number;
  label: string;
  details: string;
}

export const TrendChart: React.FC<TrendChartProps> = ({ nodes }) => {
  const { t } = useLocale();
  const [nodesStats, setNodesStats] = useState<Record<string, Snapshot[]>>({});
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [period, setPeriod] = useState<'24h' | '7d'>(
    () => (localStorage.getItem('vigile_trend_period') as '24h' | '7d') || '24h'
  );

  const handlePeriodChange = (p: '24h' | '7d') => {
    setPeriod(p);
    localStorage.setItem('vigile_trend_period', p);
  };

  useEffect(() => {
    if (nodes.length === 0) return;

    let active = true;
    const fetchAllStats = async () => {
      setIsLoading(true);
      try {
        const limit = period === '24h' ? 30 : 90;
        const promises = nodes.map(async (node) => {
          try {
            const res = await api<NodeStatsResponse>(
              `/api/nodes/${node.id}/stats?limit=${limit}`
            );
            return { nodeId: node.id, snapshots: res?.snapshots || [] };
          } catch (err) {
            console.error(`Failed to fetch stats for node ${node.id}:`, err);
            return { nodeId: node.id, snapshots: [] };
          }
        });

        const results = await Promise.all(promises);
        if (!active) return;

        const newStats: Record<string, Snapshot[]> = {};
        results.forEach(({ nodeId, snapshots }) => {
          newStats[nodeId] = snapshots;
        });
        setNodesStats(newStats);
      } catch (err) {
        console.error('Failed to fetch stats for all nodes:', err);
      } finally {
        if (active) setIsLoading(false);
      }
    };

    fetchAllStats();
    const interval = setInterval(fetchAllStats, 30000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [nodes, period]);

  const getTimelineData = (node: Node, snapshots: Snapshot[]): BarData[] => {
    const nowSec = Math.floor(Date.now() / 1000);
    const durationSec = period === '24h' ? 24 * 3600 : 7 * 24 * 3600;
    const totalBars = 30;
    const slotDurationSec = durationSec / totalBars;

    const bars: BarData[] = [];
    const isDemoNode = node.id.includes('demo');

    for (let i = 0; i < totalBars; i++) {
      const startTime = nowSec - (totalBars - i) * slotDurationSec;
      const endTime = nowSec - (totalBars - i - 1) * slotDurationSec;

      const slotSnapshots = snapshots.filter(
        (s) => s.collected_at >= startTime && s.collected_at < endTime
      );

      let status: 'ok' | 'warning' | 'critical' | 'nodata';
      let details: string;

      const dateOpts: Intl.DateTimeFormatOptions = {
        hour: '2-digit',
        minute: '2-digit',
      };
      if (period === '7d') {
        dateOpts.day = '2-digit';
        dateOpts.month = 'short';
      }
      const timeLabel = new Date(startTime * 1000).toLocaleString('fr-FR', dateOpts);

      if (isDemoNode) {
        // Simulated timeline for demo nodes to present a rich story
        if (node.id === 'demo-node-05') {
          if (i >= 18) {
            status = 'critical';
            details = 'Hors-ligne (Interruption)';
          } else if (i === 12 || i === 13) {
            status = 'warning';
            details = 'Surcharge détectée : CPU: 88%';
          } else {
            status = 'ok';
            details = `Opérationnel (CPU: ${20 + (i % 5) * 8}% | RAM: 35%)`;
          }
        } else if (node.id === 'demo-node-01') {
          // prod-web-01: online with some spikes
          if (i === 8) {
            status = 'warning';
            details = 'Surcharge détectée : CPU: 92%';
          } else if (i === 22) {
            status = 'warning';
            details = 'Surcharge détectée : RAM: 86%';
          } else {
            status = 'ok';
            details = `Opérationnel (CPU: ${15 + (i % 7) * 6}% | RAM: 45%)`;
          }
        } else if (node.id === 'demo-node-02') {
          // prod-db-01: online, stable
          if (i === 14) {
            status = 'warning';
            details = 'Surcharge détectée : Disque: 88%';
          } else {
            status = 'ok';
            details = `Opérationnel (CPU: ${10 + (i % 6) * 5}% | RAM: 58%)`;
          }
        } else if (node.id === 'demo-node-03') {
          // stg-api-01: online, normal
          status = 'ok';
          details = `Opérationnel (CPU: ${8 + (i % 4) * 4}% | RAM: 28%)`;
        } else {
          // other demo nodes
          if (i % 15 === 3) {
            status = 'warning';
            details = 'Surcharge détectée : CPU: 84%';
          } else {
            status = 'ok';
            details = `Opérationnel (CPU: ${12 + (i % 8) * 3}% | RAM: 32%)`;
          }
        }
      } else {
        // Real node logic
        if (slotSnapshots.length > 0) {
          const maxCpu = Math.max(...slotSnapshots.map((s) => s.cpu_percent));
          const maxMem = Math.max(...slotSnapshots.map((s) => s.mem_percent));
          const maxDisk = Math.max(...slotSnapshots.map((s) => s.disk_percent));

          if (maxCpu > 80 || maxMem > 80 || maxDisk > 85) {
            status = 'warning';
            const reasons: string[] = [];
            if (maxCpu > 80) reasons.push(`CPU: ${Math.round(maxCpu)}%`);
            if (maxMem > 80) reasons.push(`RAM: ${Math.round(maxMem)}%`);
            if (maxDisk > 85) reasons.push(`Disque: ${Math.round(maxDisk)}%`);
            details = `Surcharge détectée : ${reasons.join(', ')}`;
          } else {
            status = 'ok';
            details = `Opérationnel (CPU: ${Math.round(maxCpu)}% | RAM: ${Math.round(maxMem)}%)`;
          }
        } else {
          const enrolled = node.enrolled_at || node.created_at / 1000;
          if (endTime < enrolled) {
            status = 'nodata';
            details = 'Non configuré';
          } else if (!node.online && (node.last_heartbeat === null || startTime > node.last_heartbeat)) {
            status = 'critical';
            details = 'Hors-ligne (Interruption)';
          } else if (!node.online) {
            status = 'critical';
            details = 'Hors-ligne (Interruption)';
          } else {
            status = 'nodata';
            details = 'Aucune donnée reçue';
          }
        }
      }

      bars.push({
        index: i,
        startTime,
        endTime,
        status,
        details,
        label: timeLabel,
        snapshots: slotSnapshots,
      });
    }

    return bars;
  };

  const calculateUptime = (bars: BarData[]): string => {
    const activeBars = bars.filter((b) => b.status !== 'nodata');
    if (activeBars.length === 0) return '100%';
    const upBars = activeBars.filter((b) => b.status === 'ok' || b.status === 'warning');
    const pct = (upBars.length / activeBars.length) * 100;
    return pct.toFixed(1) + '%';
  };

  const getIncidents = (bars: BarData[]): IncidentPeriod[] => {
    const incidents: IncidentPeriod[] = [];
    let currentIncident: { type: 'critical' | 'warning'; startIdx: number; endIdx: number; details: string } | null = null;

    for (let idx = 0; idx < bars.length; idx++) {
      const bar = bars[idx];
      if (bar.status === 'critical' || bar.status === 'warning') {
        if (currentIncident && currentIncident.type === bar.status) {
          currentIncident.endIdx = idx;
        } else {
          if (currentIncident) {
            incidents.push({
              type: currentIncident.type,
              startTime: bars[currentIncident.startIdx].startTime,
              endTime: bars[currentIncident.endIdx].endTime,
              label: bars[currentIncident.startIdx].label,
              details: currentIncident.details,
            });
          }
          currentIncident = {
            type: bar.status,
            startIdx: idx,
            endIdx: idx,
            details: bar.details,
          };
        }
      } else {
        if (currentIncident) {
          incidents.push({
            type: currentIncident.type,
            startTime: bars[currentIncident.startIdx].startTime,
            endTime: bars[currentIncident.endIdx].endTime,
            label: bars[currentIncident.startIdx].label,
            details: currentIncident.details,
          });
          currentIncident = null;
        }
      }
    }

    if (currentIncident) {
      incidents.push({
        type: currentIncident.type,
        startTime: bars[currentIncident.startIdx].startTime,
        endTime: bars[currentIncident.endIdx].endTime,
        label: bars[currentIncident.startIdx].label,
        details: currentIncident.details,
      });
    }

    return incidents;
  };

  return (
    <div className="card w-full flex flex-col gap-5 animate-fade-in">
      <div className="flex items-center justify-between border-b border-border-strong pb-3">
        <div>
          <h4 className="text-sm font-bold text-text-1 tracking-wide uppercase flex items-center gap-1.5 font-interface">
            <Cpu size={16} className="text-accent" />
            {t('swim.trends')}
          </h4>
          <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
            Suivi de l'uptime et journal des incidents de la flotte
          </p>
        </div>

        <div className="flex bg-surface-2 border border-border rounded-lg p-0.5 select-none">
          <button
            onClick={() => handlePeriodChange('24h')}
            className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-colors cursor-pointer ${
              period === '24h' ? 'bg-accent text-white' : 'text-text-3 hover:text-text-2'
            }`}
          >
            24h
          </button>
          <button
            onClick={() => handlePeriodChange('7d')}
            className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-colors cursor-pointer ${
              period === '7d' ? 'bg-accent text-white' : 'text-text-3 hover:text-text-2'
            }`}
          >
            7j
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-6">
        {isLoading && Object.keys(nodesStats).length === 0 ? (
          <div className="py-8 flex items-center justify-center">
            <ChartSkeleton />
          </div>
        ) : nodes.length === 0 ? (
          <div className="py-8 text-center text-xs text-text-3 italic">
            Aucun serveur configuré.
          </div>
        ) : (
          nodes.map((node) => {
            const nodeSnaps = nodesStats[node.id] || [];
            const timelineBars = getTimelineData(node, nodeSnaps);
            const uptimePct = calculateUptime(timelineBars);
            const nodeIncidents = getIncidents(timelineBars);

            return (
              <div key={node.id} className="flex flex-col gap-2.5 p-4 rounded-xl border border-border bg-surface/40 hover:border-border-strong hover:bg-surface-2/10 transition-all duration-300">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        node.online
                          ? 'bg-severity-ok shadow-[0_0_8px_var(--severity-ok)]'
                          : 'bg-severity-critical shadow-[0_0_8px_var(--severity-critical)] animate-pulse'
                      }`}
                    />
                    <span className="font-bold text-xs text-text-1">{node.name}</span>
                    <span className="text-[10px] text-text-3 font-mono truncate max-w-[120px] sm:max-w-none">
                      {node.hostname || 'no-hostname'}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-text-3 uppercase tracking-wider">Uptime:</span>
                    <span className={`text-xs font-mono font-bold ${
                      uptimePct === '100.0%' || uptimePct === '100%'
                        ? 'text-severity-ok'
                        : uptimePct.startsWith('99')
                        ? 'text-severity-warning'
                        : 'text-severity-critical'
                    }`}>
                      {uptimePct}
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-1 py-1.5">
                    {timelineBars.map((bar, barIdx) => {
                      let colorClass = 'bg-text-3/20'; // nodata
                      if (bar.status === 'ok') colorClass = 'bg-severity-ok/70 hover:bg-severity-ok';
                      if (bar.status === 'warning') colorClass = 'bg-severity-warning/70 hover:bg-severity-warning';
                      if (bar.status === 'critical') colorClass = 'bg-severity-critical/70 hover:bg-severity-critical';

                      return (
                        <div
                          key={barIdx}
                          title={`${bar.label} : ${bar.details}`}
                          className={`flex-1 h-6 rounded-sm transition-transform duration-100 hover:scale-y-125 cursor-pointer relative group ${colorClass}`}
                        >
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-50 pointer-events-none">
                            <div className="bg-surface-2 border border-border-strong text-text-1 text-[10px] rounded p-2 shadow-xl whitespace-nowrap flex flex-col gap-0.5">
                              <span className="font-mono text-text-3">{bar.label}</span>
                              <span className="font-semibold">{bar.details}</span>
                            </div>
                            <div className="w-1.5 h-1.5 bg-surface-2 border-r border-b border-border-strong rotate-45 absolute -bottom-1 left-1/2 -translate-x-1/2 z-40" />
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex items-center justify-between text-[9px] text-text-3 font-semibold uppercase tracking-wider">
                    <span>
                      {period === '24h' ? 'Il y a 24 heures' : 'Il y a 7 jours'}
                    </span>
                    <span className="w-12 h-[1px] bg-border-strong/40 flex-1 mx-2" />
                    <span>Maintenant</span>
                  </div>
                </div>

                <div className="mt-1 text-[10px] border-t border-border/20 pt-2">
                  {nodeIncidents.length === 0 ? (
                    <div className="flex items-center gap-1.5 text-severity-ok font-medium">
                      <span className="w-1.5 h-1.5 rounded-full bg-severity-ok shrink-0" />
                      <span>Aucun incident signalé sur la période. Fonctionnement nominal.</span>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center gap-1.5 text-severity-warning font-bold uppercase tracking-wider text-[9px]">
                        <span>Journal des incidents ({nodeIncidents.length}) :</span>
                      </div>
                      <div className="flex flex-col gap-1 max-h-24 overflow-y-auto pr-1">
                        {nodeIncidents.map((inc, incIdx) => {
                          const isCrit = inc.type === 'critical';
                          return (
                            <div key={incIdx} className="flex items-start justify-between gap-4 py-1 px-2.5 rounded bg-surface-3/20 border border-border/30">
                              <div className="flex items-center gap-2">
                                <span className={`w-1 h-1 rounded-full shrink-0 ${isCrit ? 'bg-severity-critical animate-pulse' : 'bg-severity-warning'}`} />
                                <span className={isCrit ? 'text-severity-critical font-bold' : 'text-severity-warning font-bold'}>
                                  {isCrit ? 'Coupure' : 'Alerte'}
                                </span>
                                <span className="text-text-2">— {inc.details}</span>
                              </div>
                              <span className="text-text-3 font-mono text-[9px] whitespace-nowrap">
                                {inc.label}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
