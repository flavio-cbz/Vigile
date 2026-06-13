import React, { useState, useEffect } from 'react';

interface TimeAgoProps {
  timestamp: string | number | null;
  className?: string;
}

export const TimeAgo: React.FC<TimeAgoProps> = ({ timestamp, className = '' }) => {
  const [timeAgo, setTimeAgo] = useState('');

  useEffect(() => {
    if (!timestamp) {
      setTimeAgo('jamais');
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
        setTimeAgo('inconnu');
        return;
      }

      const now = Date.now();
      const seconds = Math.floor((now - parsedTime) / 1000);

      if (seconds < 5) {
        setTimeAgo("à l'instant");
        return;
      }
      if (seconds < 60) {
        setTimeAgo(`il y a ${seconds}s`);
        return;
      }
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) {
        setTimeAgo(`il y a ${minutes}m`);
        return;
      }
      const hours = Math.floor(minutes / 60);
      if (hours < 24) {
        setTimeAgo(`il y a ${hours}h`);
        return;
      }
      const days = Math.floor(hours / 24);
      setTimeAgo(`il y a ${days}j`);
    };

    calculateTime();
    const interval = setInterval(calculateTime, 30000); // refresh every 30s

    return () => clearInterval(interval);
  }, [timestamp]);

  return (
    <span className={`text-text-3 font-mono text-[10px] whitespace-nowrap ${className}`} title={timestamp ? new Date(timestamp).toLocaleString() : ''}>
      {timeAgo}
    </span>
  );
};
