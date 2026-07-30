import React, { useState, useEffect } from 'react';
import { Cpu } from 'lucide-react';
import { api } from '../../hooks/useApi';
import { useLocale } from '../../i18n';
import { ChartSkeleton } from '../ui/CardSkeleton';
import { logger } from '../../lib/logger';
import type { Node } from '../../store/nodeStore';
import type { Snapshot } from './TrendBar';
import { PeriodSelector } from './PeriodSelector';
import { TrendChartNode } from './TrendChartNode';
import { getTimelineData, calculateUptime, getIncidents } from './trendDataUtils';

interface NodeStatsResponse {
  node_id: string;
  snapshots: Snapshot[];
}

interface TrendChartProps {
  nodes: Node[];
}

export const TrendChart: React.FC<TrendChartProps> = ({ nodes }) => {
  const { t } = useLocale();
  const [nodesStats, setNodesStats] = useState<Record<string, Snapshot[]>>({});
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [hoveredBar, setHoveredBar] = useState<{ nodeIdx: number; barIdx: number } | null>(null);
  const [period, setPeriod] = useState<'24h' | '7d'>(
    () => (localStorage.getItem('vigile_trend_period') as '24h' | '7d') || '24h'
  );
  const [nowSec, setNowSec] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const interval = setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 15000);
    return () => clearInterval(interval);
  }, []);

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
            logger.error(`Failed to fetch stats for node ${node.id}:`, err);
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
        logger.error('Failed to fetch stats for all nodes:', err);
      } finally {
        if (active) setIsLoading(false);
      }
    };

    fetchAllStats();
    const interval = setInterval(fetchAllStats, 45000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [nodes, period]);

  return (
    <div className="card w-full flex flex-col gap-5 animate-fade-in">
      <div className="flex items-center justify-between border-b border-border-strong pb-3">
        <div>
          <h4 className="text-sm font-bold text-text-1 tracking-wide uppercase flex items-center gap-1.5 font-interface">
            <Cpu size={16} className="text-accent" />
            {t('swim.trends')}
          </h4>
          <p className="text-[10px] text-text-3 font-semibold uppercase tracking-wider mt-0.5">
            {t('trend.subtitle')}
          </p>
        </div>

        <PeriodSelector period={period} onPeriodChange={handlePeriodChange} />
      </div>

      <div className="flex flex-col gap-6">
        {isLoading && Object.keys(nodesStats).length === 0 ? (
          <div className="py-8 flex items-center justify-center">
            <ChartSkeleton />
          </div>
        ) : nodes.length === 0 ? (
          <div className="py-8 text-center text-xs text-text-3 italic">
            {t('trend.empty')}
          </div>
        ) : (
          nodes.map((node, nodeIdx) => {
            const nodeSnaps = nodesStats[node.id] || [];
            const timelineBars = getTimelineData(node, nodeSnaps, nowSec, period, t);
            const uptimePct = calculateUptime(timelineBars);
            const nodeIncidents = getIncidents(timelineBars);

            return (
              <TrendChartNode
                key={node.id}
                node={node}
                nodeIdx={nodeIdx}
                timelineBars={timelineBars}
                uptimePct={uptimePct}
                nodeIncidents={nodeIncidents}
                hoveredBar={hoveredBar}
                onBarHover={setHoveredBar}
              />
            );
          })
        )}
      </div>
    </div>
  );
};
