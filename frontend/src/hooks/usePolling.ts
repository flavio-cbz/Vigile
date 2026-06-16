import { useEffect, useRef } from 'react';

const activeCallbacks = new Map<string, Set<() => void>>();
const activeIntervals = new Map<string, ReturnType<typeof setInterval>>();

export function usePolling(
  key: string,
  callback: () => void,
  intervalMs: number,
  enabled = true,
) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled) return;

    if (!activeCallbacks.has(key)) {
      activeCallbacks.set(key, new Set());
    }
    const callbacks = activeCallbacks.get(key)!;

    // Wrapper local qui pointe vers le callback à jour à chaque render
    const wrapper = () => {
      savedCallback.current();
    };
    callbacks.add(wrapper);

    if (!activeIntervals.has(key)) {
      callback();
      const id = setInterval(() => {
        const currentCallbacks = activeCallbacks.get(key);
        if (currentCallbacks) {
          currentCallbacks.forEach(cb => cb());
        }
      }, intervalMs);
      activeIntervals.set(key, id);
    }

    return () => {
      const currentCallbacks = activeCallbacks.get(key);
      if (currentCallbacks) {
        currentCallbacks.delete(wrapper);
        if (currentCallbacks.size === 0) {
          activeCallbacks.delete(key);
          const id = activeIntervals.get(key);
          if (id) {
            clearInterval(id);
            activeIntervals.delete(key);
          }
        }
      }
    };
  }, [key, intervalMs, enabled]);
}
