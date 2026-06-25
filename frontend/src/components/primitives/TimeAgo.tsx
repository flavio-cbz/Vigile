import React, { useState, useEffect } from 'react';
import { useLocale } from '../../i18n';

interface TimeAgoProps {
  timestamp: string | number | null;
  className?: string;
}

export const TimeAgo: React.FC<TimeAgoProps> = ({ timestamp, className = '' }) => {
  const { t } = useLocale();
  const [timeAgo, setTimeAgo] = useState('');

  useEffect(() => {
    if (!timestamp) {
      setTimeAgo(t('common.never'));
      return;
    }

    const calculateTime = () => {
      let parsedTime: number;
      if (typeof timestamp === 'string') {
        parsedTime = new Date(timestamp).getTime();
      } else {
        // If Unix timestamp is in seconds, convert to milliseconds
        parsedTime = timestamp < 9999999999 ? timestamp * 1000 : timestamp;
      }

      if (isNaN(parsedTime)) {
        setTimeAgo(t('common.unknown'));
        return;
      }

      const now = Date.now();
      const seconds = Math.floor((now - parsedTime) / 1000);

      if (seconds < 5) {
        setTimeAgo(t('common.just_now'));
        return;
      }
      if (seconds < 60) {
        setTimeAgo(t('common.ago_seconds', { n: seconds }));
        return;
      }
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) {
        setTimeAgo(t('common.ago_minutes', { n: minutes }));
        return;
      }
      const hours = Math.floor(minutes / 60);
      if (hours < 24) {
        setTimeAgo(t('common.ago_hours', { n: hours }));
        return;
      }
      const days = Math.floor(hours / 24);
      setTimeAgo(t('common.ago_days', { n: days }));
    };

    calculateTime();
    const interval = setInterval(calculateTime, 30000);

    return () => clearInterval(interval);
  }, [timestamp]);

  return (
    <span className={`text-text-3 font-mono text-[10px] whitespace-nowrap ${className}`} title={timestamp ? new Date(timestamp).toLocaleString() : ''}>
      {timeAgo}
    </span>
  );
};
