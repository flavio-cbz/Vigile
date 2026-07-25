import React, { useState, useEffect } from 'react';
import { useLocale } from '../../i18n';

interface TimeAgoProps {
  timestamp: string | number | null;
  className?: string;
}

function computeTimeAgo(timestamp: string | number | null, t: (k: string, variables?: Record<string, string | number>) => string): string {
  if (!timestamp) return t('common.never');

  let parsedTime: number;
  if (typeof timestamp === 'string') {
    parsedTime = new Date(timestamp).getTime();
  } else {
    parsedTime = timestamp < 9999999999 ? timestamp * 1000 : timestamp;
  }

  if (isNaN(parsedTime)) return t('common.unknown');

  const now = Date.now();
  const seconds = Math.floor((now - parsedTime) / 1000);

  if (seconds < 5) return t('common.just_now');
  if (seconds < 60) return t('common.ago_seconds', { n: seconds });

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t('common.ago_minutes', { n: minutes });

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('common.ago_hours', { n: hours });

  const days = Math.floor(hours / 24);
  return t('common.ago_days', { n: days });
}

export const TimeAgo: React.FC<TimeAgoProps> = ({ timestamp, className = '' }) => {
  const { t } = useLocale();
  const [timeAgo, setTimeAgo] = useState(() => computeTimeAgo(timestamp, t));

  useEffect(() => {
    const tick = () => setTimeAgo(computeTimeAgo(timestamp, t));
    tick();
    const interval = setInterval(tick, 30000);
    return () => clearInterval(interval);
  }, [timestamp, t]);

  return (
    <span className={`text-text-3 font-mono text-[10px] whitespace-nowrap ${className}`} title={timestamp ? new Date(timestamp).toLocaleString() : ''}>
      {timeAgo}
    </span>
  );
};
