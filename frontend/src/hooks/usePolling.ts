import { useEffect, useRef } from 'react';

// Shared interval registry — keyed map prevents duplicate polling intervals
// when multiple components subscribe to the same key.
const activePolls = new Map<string, ReturnType<typeof setInterval>>();
const subscriberCounts = new Map<string, number>();

export function usePolling(
  key: string,
  callback: () => void,
  intervalMs: number,
) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    // Register subscriber
    subscriberCounts.set(key, (subscriberCounts.get(key) || 0) + 1);

    // Only start interval if first subscriber
    if (!activePolls.has(key)) {
      callback(); // immediate first call
      const id = setInterval(() => {
        savedCallback.current();
      }, intervalMs);
      activePolls.set(key, id);
    }

    return () => {
      // Unregister subscriber
      const count = (subscriberCounts.get(key) || 1) - 1;
      if (count <= 0) {
        subscriberCounts.delete(key);
        const id = activePolls.get(key);
        if (id) {
          clearInterval(id);
          activePolls.delete(key);
        }
      } else {
        subscriberCounts.set(key, count);
      }
    };
  }, [key, intervalMs]);
}
