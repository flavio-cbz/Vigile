import type { Node } from '../../store/nodeStore';
import type { BarData, Snapshot } from './TrendBar';

export interface IncidentPeriod {
  type: 'critical' | 'warning';
  startTime: number;
  endTime: number;
  label: string;
  details: string;
}

export function getTimelineData(
  node: Node,
  snapshots: Snapshot[],
  nowSec: number,
  period: '24h' | '7d',
  t: (key: string) => string,
): BarData[] {
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
          details = t('trend.outage');
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
          details = t('common.unknown');
        } else if (!node.online && (node.last_heartbeat === null || startTime > node.last_heartbeat)) {
          status = 'critical';
          details = t('trend.outage');
        } else if (!node.online) {
          status = 'critical';
          details = t('trend.outage');
        } else {
          status = 'nodata';
          details = t('common.unknown');
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
}

export function calculateUptime(bars: BarData[]): string {
  const activeBars = bars.filter((b) => b.status !== 'nodata');
  if (activeBars.length === 0) return '100%';
  const upBars = activeBars.filter((b) => b.status === 'ok' || b.status === 'warning');
  const pct = (upBars.length / activeBars.length) * 100;
  return pct.toFixed(1) + '%';
}

export function getIncidents(bars: BarData[]): IncidentPeriod[] {
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
}
