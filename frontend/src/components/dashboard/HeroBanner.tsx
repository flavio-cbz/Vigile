import React, { useState, useEffect, memo } from 'react';
import { AlertTriangle, CheckCircle, AlertOctagon, RefreshCw } from 'lucide-react';
import { useLocale } from '../../i18n';
import type { Node } from '../../store/nodeStore';

interface HeroBannerProps {
  nodes: Node[];
  lastUpdated: number | null;
  topInsight?: {
    severity: string;
    headline: string;
    detail: string;
  } | null;
}

const LastUpdatedBadge: React.FC<{ lastUpdated: number | null }> = memo(({ lastUpdated }) => {
  const { t } = useLocale();
  const [secondsAgo, setSecondsAgo] = useState<number>(0);

  useEffect(() => {
    if (!lastUpdated) return;
    const tick = () => setSecondsAgo(Math.floor((Date.now() - lastUpdated) / 1000));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [lastUpdated]);

  if (!lastUpdated) {
    return (
      <span className="text-[11px] font-mono text-ink-secondary">
        {t('hero.waiting_update')}
      </span>
    );
  }

  const isStale = secondsAgo > 60;

  return (
    <span className={`text-[11px] font-mono flex items-center gap-1.5 ${isStale ? 'text-danger font-bold' : 'text-ink-secondary'}`}>
      <RefreshCw size={12} className={isStale ? 'animate-spin' : ''} />
      {isStale ? t('dash.stale_warning') : t('dash.last_updated', { time: secondsAgo })}
    </span>
  );
});

LastUpdatedBadge.displayName = 'LastUpdatedBadge';

export const HeroBanner: React.FC<HeroBannerProps> = memo(({ nodes, lastUpdated, topInsight }) => {
  const { t } = useLocale();

  const total = nodes.length;
  const online = nodes.filter((n) => n.online).length;
  const offlineNodes = nodes.filter((n) => !n.online);
  const offlineCount = offlineNodes.length;

  if (total === 0) {
    return (
      <div className="p-6 rounded-xl border border-border bg-surface-1 flex flex-col sm:flex-row items-center justify-between gap-4 animate-fade-in">
        <div className="flex items-center gap-3">
          <AlertTriangle className="text-warning w-8 h-8 animate-pulse-subtle" />
          <div>
            <h2 className="text-base font-semibold text-ink-primary">
              {t('add_node.title')}
            </h2>
            <p className="text-xs text-ink-secondary">
              {t('hero.add_first')}
            </p>
          </div>
        </div>
        <button
          onClick={() => window.location.href = '/servers'}
          className="mt-3 px-3 py-1.5 text-[10px] font-bold font-interface uppercase tracking-wider bg-accent/10 border border-accent/20 text-accent rounded hover:bg-accent/20 transition-colors cursor-pointer"
        >
          {t('hero.add_action')}
        </button>
      </div>
    );
  }

  let status: 'ok' | 'warn' | 'crit' = 'ok';
  let titleOverride: string | null = null;
  let descOverride: string | null = null;

  if (offlineCount === total) {
    status = 'crit';
  } else if (topInsight && topInsight.severity === 'critical') {
    status = 'crit';
    titleOverride = `Attention requise — ${topInsight.headline}`;
    descOverride = `${topInsight.detail} · ${online}/${total} serveurs en ligne`;
  } else if (topInsight && topInsight.severity === 'warning') {
    status = 'warn';
    titleOverride = `Attention requise — ${topInsight.headline}`;
    descOverride = `${topInsight.detail} · ${online}/${total} serveurs en ligne`;
  } else if (offlineCount > 0) {
    status = 'warn';
  }

  const statusStyles = {
    ok: {
      gradient: 'var(--gradient-hero-ok)',
      border: 'border-success/20',
      icon: <CheckCircle className="w-8 h-8 text-success" />,
      title: t('dash.all_operational'),
      desc: t('dash.servers_online', { online, total }),
    },
    warn: {
      gradient: 'var(--gradient-hero-warn)',
      border: 'border-warning/20',
      icon: <AlertTriangle className="w-8 h-8 text-warning animate-pulse-subtle" />,
      title: titleOverride || t('dash.servers_offline_banner', {
        count: offlineCount,
        names: offlineNodes.map((n) => n.name).join(', ')
      }),
      desc: descOverride || t('dash.servers_online', { online, total }),
    },
    crit: {
      gradient: 'var(--gradient-hero-crit)',
      border: 'border-danger/30',
      icon: <AlertOctagon className="w-8 h-8 text-danger animate-pulse-subtle" />,
      title: titleOverride || t("hero.all_offline_title"),
      desc: descOverride || t("hero.all_offline_description"),
    },
  };

  const current = statusStyles[status];

  return (
    <div
      className={`p-4 sm:p-6 rounded-xl border ${current.border} flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4 transition-all duration-300 animate-fade-in`}
      style={{ background: current.gradient }}
    >
      <div className="flex items-center gap-4">
        <div className="shrink-0">{current.icon}</div>
        <div>
          <h2 className="text-lg font-bold text-ink-primary tracking-tight">
            {current.title}
          </h2>
          <p className="text-xs text-ink-secondary mt-0.5">
            {current.desc}
          </p>
        </div>
      </div>
      <div className="flex flex-col items-end gap-1.5 shrink-0 text-right">
        <LastUpdatedBadge lastUpdated={lastUpdated} />
      </div>
    </div>
  );
});

HeroBanner.displayName = 'HeroBanner';
