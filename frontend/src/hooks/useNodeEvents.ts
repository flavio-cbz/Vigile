import { useEffect } from 'react';
import { useNodeStore, type NodeDeletedEvent, type NodeStateChangeEvent } from '../store/nodeStore';
import { useToastStore } from '../store/useToastStore';
import { useLocale } from '../i18n';
import { logger } from '../lib/logger';

export function useNodeEvents(): void {
  const { t } = useLocale();
  const applyEvent = useNodeStore((s) => s.applyEvent);
  const applyDeletedEvent = useNodeStore((s) => s.applyDeletedEvent);
  const openServerConfig = useNodeStore((s) => s.openServerConfig);
  const addToast = useToastStore((s) => s.addToast);

  useEffect(() => {
    const token = localStorage.getItem('vigile_access_token');
    if (!token) return;
    const url = `/api/nodes/events/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);

    es.addEventListener('node.state', (e) => {
      try {
        const payload = JSON.parse((e as MessageEvent).data) as NodeStateChangeEvent;
        applyEvent(payload);

        if (payload.new_state === 'UNCONFIGURED') {
          const node = useNodeStore.getState().nodes.find((n) => n.id === payload.node_id);
          if (node) {
            addToast('success', t('node_events.new_server'), node.hostname || node.name);
            openServerConfig(node);
          }
        }
      } catch (err) {
        logger.error('SSE parse error', err);
      }
    });

    es.addEventListener('node.deleted', (e) => {
      try {
        const payload = JSON.parse((e as MessageEvent).data) as NodeDeletedEvent;
        applyDeletedEvent(payload);
      } catch (err) {
        logger.error('SSE parse error', err);
      }
    });

    es.onerror = () => {
      logger.warn('SSE connection error, will retry');
    };

    return () => {
      es.close();
    };
  }, [applyEvent, applyDeletedEvent, openServerConfig, addToast, t]);
}
