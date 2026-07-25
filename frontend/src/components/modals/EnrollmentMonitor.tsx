import React, { useState, useEffect, useRef } from 'react';
import { api } from '../../hooks/useApi';
import type { Node } from '../../store/nodeStore';

const POLL_INTERVAL_MS = 5000;
const ENROLLMENT_AUTO_CLOSE_MS = 2500;

interface EnrollmentMonitorProps {
  nodeId: string;
  onEnrolled: () => void;
  onClose: () => void;
  children: (isEnrolled: boolean) => React.ReactNode;
}

/**
 * Headless component that polls for worker enrollment and auto-closes
 * the modal after a brief success animation. Passes `isEnrolled` to
 * its render-prop child so the parent can adapt the UI.
 */
export const EnrollmentMonitor = ({
  nodeId,
  onEnrolled,
  onClose,
  children,
}: EnrollmentMonitorProps) => {
  const [isEnrolled, setIsEnrolled] = useState(false);
  const closeTimerRef = useRef<number | null>(null);

  // Keep refs so the polling interval always reads the latest callbacks
  // without being recreated on every parent render.
  const onCloseRef = useRef(onClose);
  const onEnrolledRef = useRef(onEnrolled);

  useEffect(() => {
    onCloseRef.current = onClose;
    onEnrolledRef.current = onEnrolled;
  });

  // ---- Enrollment polling ----
  useEffect(() => {
    if (!nodeId || isEnrolled) return;

    const intervalId = setInterval(async () => {
      try {
        const nodes = await api<Node[]>('/api/nodes', { skipToast: true });
        if (nodes) {
          const enrolledNode = nodes.find((n) => n.id === nodeId);
          if (enrolledNode && enrolledNode.online) {
            setIsEnrolled(true);
            clearInterval(intervalId);
            onEnrolledRef.current();
            closeTimerRef.current = window.setTimeout(() => {
              onCloseRef.current();
            }, ENROLLMENT_AUTO_CLOSE_MS);
          }
        }
      } catch (err) {
        console.error('Error polling node enrollment:', err);
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, [nodeId, isEnrolled]);

  // ---- Cleanup auto-close timer on unmount ----
  useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    };
  }, []);

  return <>{children(isEnrolled)}</>;
};
