import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { RefreshCw, CheckCircle, AlertTriangle, XCircle, HelpCircle } from 'lucide-react';

interface UptimeTrackerProps {
  nodeId: string;
  isOnline: boolean;
  compact?: boolean;
}

interface SnapshotData {
  collected_at: number;
  cpu_percent: number;
  mem_percent: number;
  disk_percent: number;
}

interface BarState {
  status: 'operational' | 'degraded' | 'offline' | 'nodata';
  timestamp: string;
  detail: string;
}

export const UptimeTracker: React.FC<UptimeTrackerProps> = ({ nodeId, isOnline, compact = false }) => {
  const { accessToken, user } = useAuthStore();
  const isDemo = user?.username === 'demo';

  const [loading, setLoading] = useState(false);
  const [bars, setBars] = useState<BarState[]>([]);
  const [uptimeScore, setUptimeScore] = useState<number>(100);
  const [hoveredBar, setHoveredBar] = useState<BarState | null>(null);

  const barCount = compact ? 20 : 30;

  const fetchHistory = async () => {
    if (isDemo) {
      // Mock data for demo mode
      const mockBars: BarState[] = [];
      const now = Math.floor(Date.now() / 1000);
      
      for (let i = 0; i < barCount; i++) {
        const timeOffset = (barCount - i) * 60; // 1 min intervals
        const timeStr = new Date((now - timeOffset) * 1000).toLocaleString('fr-FR');
        
        let status: 'operational' | 'degraded' | 'offline' | 'nodata' = 'operational';
        let detail = 'Système opérationnel — CPU & RAM stables';
        
        // Add some variety to demo status grid
        if (i === 12) {
          status = 'degraded';
          detail = 'Statut dégradé — Charge CPU élevée (84%)';
        } else if (i === 24) {
          status = 'degraded';
          detail = 'Statut dégradé — Mémoire saturée (89%)';
        } else if (i === 18 || i === 19) {
          status = 'offline';
          detail = 'Hors ligne — Perte de heartbeat';
        } else if (i < 2) {
          status = 'nodata';
          detail = 'Données manquantes';
        }
        
        mockBars.push({ status, timestamp: timeStr, detail });
      }

      // If the node is currently offline, override the last bar
      if (!isOnline && mockBars.length > 0) {
        mockBars[mockBars.length - 1] = {
          status: 'offline',
          timestamp: new Date().toLocaleString('fr-FR'),
          detail: 'Hors ligne — Serveur injoignable'
        };
      }

      setBars(mockBars);
      calculateUptime(mockBars);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`/api/nodes/${nodeId}/stats?limit=${barCount}`, {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        const rawSnaps: SnapshotData[] = data.snapshots || [];
        
        // Sort chronologically (oldest to newest)
        const snaps = [...rawSnaps].reverse();
        
        const processedBars: BarState[] = [];
        
        // Pad with 'nodata' if we have fewer snapshots than barCount
        const paddingNeeded = barCount - snaps.length;
        for (let i = 0; i < paddingNeeded; i++) {
          processedBars.push({
            status: 'nodata',
            timestamp: 'N/A',
            detail: 'Données insuffisantes pour cet intervalle'
          });
        }
        
        // Process each snapshot
        snaps.forEach((snap, idx) => {
          const timeStr = new Date(snap.collected_at * 1000).toLocaleString('fr-FR');
          let status: 'operational' | 'degraded' | 'offline' = 'operational';
          let detail = `Opérationnel — CPU: ${Math.round(snap.cpu_percent)}%, RAM: ${Math.round(snap.mem_percent)}%`;
          
          // Check for degraded state
          if (snap.cpu_percent >= 80 || snap.mem_percent >= 85 || snap.disk_percent >= 85) {
            status = 'degraded';
            const reasons: string[] = [];
            if (snap.cpu_percent >= 80) reasons.push(`CPU: ${Math.round(snap.cpu_percent)}%`);
            if (snap.mem_percent >= 85) reasons.push(`RAM: ${Math.round(snap.mem_percent)}%`);
            if (snap.disk_percent >= 85) reasons.push(`Disque: ${Math.round(snap.disk_percent)}%`);
            detail = `Charge dégradée — ${reasons.join(', ')}`;
          }
          
          // Check for offline gaps (e.g. > 3 minutes between snapshots)
          if (idx > 0) {
            const prevSnap = snaps[idx - 1];
            const gap = snap.collected_at - prevSnap.collected_at;
            if (gap > 180) { // More than 3 minutes gap
              status = 'offline';
              detail = `Hors ligne — Interruption de signal de ${Math.round(gap / 60)} minutes`;
            }
          }
          
          processedBars.push({ status, timestamp: timeStr, detail });
        });
        
        // Handle current offline status override
        if (!isOnline && processedBars.length > 0) {
          processedBars[processedBars.length - 1] = {
            status: 'offline',
            timestamp: new Date().toLocaleString('fr-FR'),
            detail: 'Hors ligne — Pas de signal actif actuellement'
          };
        }
        
        setBars(processedBars);
        calculateUptime(processedBars);
      }
    } catch (e) {
      console.error('Failed to load uptime stats', e);
    } finally {
      setLoading(false);
    }
  };

  const calculateUptime = (barStates: BarState[]) => {
    const activeBars = barStates.filter(b => b.status !== 'nodata');
    if (activeBars.length === 0) {
      setUptimeScore(100);
      return;
    }
    const onlineCount = activeBars.filter(b => b.status !== 'offline').length;
    const score = (onlineCount / activeBars.length) * 100;
    setUptimeScore(Math.round(score * 10) / 10); // Round to 1 decimal place
  };

  useEffect(() => {
    fetchHistory();
    // Poll every 30s to keep uptime grid alive
    const interval = setInterval(fetchHistory, 30000);
    return () => clearInterval(interval);
  }, [nodeId, isOnline]);

  const getStatusColorClass = (status: BarState['status']) => {
    switch (status) {
      case 'operational':
        return 'bg-green-custom shadow-[0_0_2px_rgba(94,196,122,0.3)] hover:bg-green-custom/80';
      case 'degraded':
        return 'bg-amber-custom shadow-[0_0_2px_rgba(212,168,80,0.3)] hover:bg-amber-custom/80';
      case 'offline':
        return 'bg-red-custom shadow-[0_0_2px_rgba(224,112,112,0.3)] hover:bg-red-custom/80';
      case 'nodata':
      default:
        return 'bg-border-strong opacity-35 hover:opacity-60';
    }
  };

  const getStatusIcon = (status: BarState['status']) => {
    switch (status) {
      case 'operational':
        return <CheckCircle className="w-3.5 h-3.5 text-green-custom" />;
      case 'degraded':
        return <AlertTriangle className="w-3.5 h-3.5 text-amber-custom" />;
      case 'offline':
        return <XCircle className="w-3.5 h-3.5 text-red-custom" />;
      case 'nodata':
      default:
        return <HelpCircle className="w-3.5 h-3.5 text-ink-muted" />;
    }
  };

  if (compact) {
    // Mini compact version for dashboard cards
    return (
      <div className="space-y-1.5 w-full">
        <div className="flex justify-between items-center text-[0.5625rem] font-bold text-ink-muted">
          <span>Uptime</span>
          <span className={uptimeScore === 100 ? 'text-green-custom' : uptimeScore > 90 ? 'text-amber-custom' : 'text-red-custom'}>
            {uptimeScore}%
          </span>
        </div>
        <div className="flex items-center gap-[3px] h-3 w-full overflow-hidden">
          {bars.map((bar, i) => (
            <div
              key={i}
              className={`flex-1 h-3 rounded-[1px] transition-all duration-150 ${getStatusColorClass(bar.status)}`}
              title={`${bar.timestamp}: ${bar.detail}`}
            />
          ))}
        </div>
      </div>
    );
  }

  // Full detailed version for NodeDetail
  return (
    <div className="glass-panel p-4 rounded-xl border border-border-custom relative space-y-3 select-none">
      <div className="flex justify-between items-center pb-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[0.6875rem] font-extrabold text-ink uppercase tracking-wider">
            Historique de Disponibilité (Derniers intervalles)
          </span>
          {loading && <RefreshCw className="w-3 h-3 text-accent-custom animate-spin shrink-0" />}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[0.625rem] font-medium text-ink-muted">Uptime récent :</span>
          <span className={`text-xs font-black font-mono ${uptimeScore === 100 ? 'text-green-custom' : uptimeScore > 90 ? 'text-amber-custom' : 'text-red-custom'}`}>
            {uptimeScore}%
          </span>
        </div>
      </div>

      {/* Grid of status bars */}
      <div className="relative">
        <div className="flex items-center gap-[4px] w-full h-8 justify-between">
          {bars.map((bar, i) => (
            <div
              key={i}
              onMouseEnter={() => setHoveredBar(bar)}
              onMouseLeave={() => setHoveredBar(null)}
              className={`flex-1 h-7 rounded-[2px] transition-all duration-150 cursor-pointer hover:scale-y-110 ${getStatusColorClass(bar.status)}`}
            />
          ))}
        </div>
        
        {/* Axis Labels */}
        <div className="flex justify-between text-[0.5625rem] text-ink-muted font-mono pt-1">
          <span>Il y a {barCount} snapshots</span>
          <span>En direct</span>
        </div>
      </div>

      {/* Hover Tooltip display at the bottom (saves layout space and looks very professional) */}
      <div className="h-9 px-3 py-1.5 rounded bg-surface border border-border-strong text-[0.6875rem] flex items-center justify-between transition-all duration-200">
        {hoveredBar ? (
          <>
            <div className="flex items-center gap-2 font-medium">
              {getStatusIcon(hoveredBar.status)}
              <span className="text-ink truncate max-w-[280px] sm:max-w-md">{hoveredBar.detail}</span>
            </div>
            <span className="font-mono text-ink-dim shrink-0 text-[0.5625rem]">{hoveredBar.timestamp}</span>
          </>
        ) : (
          <span className="text-ink-muted italic flex items-center gap-1">
            <HelpCircle className="w-3.5 h-3.5" />
            Survolez une barre d'état pour obtenir des diagnostics détaillés.
          </span>
        )}
      </div>
    </div>
  );
};
