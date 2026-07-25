import { formatActorName } from './formatActor';

export interface AuditEntryLike {
  action: string;
  actor?: string;
  user_id: string;
  details?: Record<string, unknown>;
}

/**
 * Formats a raw audit log entry and its details into a friendly, natural language string.
 * Uses translation system via passed `t` function to maintain localized text (FR/EN).
 */
export function formatAuditText(
  entry: AuditEntryLike,
  t: (key: string, variables?: Record<string, string | number>) => string
): string {
  const details = entry.details || {};
  const action = entry.action.toUpperCase();
  const actor = formatActorName(entry.actor || entry.user_id);

  const str = (key: string): string => {
    const v = details[key];
    return typeof v === 'string' ? v : '';
  };

  switch (action) {
    case 'USER_LOGIN':
      return t('audit.event.user_login', { username: str('username') || actor });
    case 'USER_LOGOUT':
      return t('audit.event.user_logout', { username: str('username') || actor });
    case 'USER_CHANGE_PASSWORD':
      return t('audit.event.user_change_password', { username: str('username') || actor });
    case 'REFRESH_THEFT_DETECTED':
      return t('audit.event.refresh_theft');
    case 'PROPOSAL_APPROVED': {
      const propAction = str('action');
      const propTarget = str('target') || str('container') || str('service');
      const translatedAction = propAction
        ? t(`audit.action.${propAction}`)
        : '';
      const actionDesc = propTarget
        ? `${translatedAction} ${propTarget}`
        : (translatedAction || t('audit.event.generic_action'));
      return t('audit.event.proposal_approved', {
        action: actionDesc,
        actor: actor,
      });
    }
    case 'PROPOSAL_REJECTED': {
      const propAction = str('action');
      const propTarget = str('target') || str('container') || str('service');
      const translatedAction = propAction
        ? t(`audit.action.${propAction}`)
        : '';
      const actionDesc = propTarget
        ? `${translatedAction} ${propTarget}`
        : (translatedAction || t('audit.event.generic_action'));
      const reason = str('reason');

      if (reason) {
        return t('audit.event.proposal_rejected_reason', {
          action: actionDesc,
          actor: actor,
          reason: reason,
        });
      }
      return t('audit.event.proposal_rejected', {
        action: actionDesc,
        actor: actor,
      });
    }
    case 'NODE_ENROLLED':
      return t('audit.event.node_enrolled', { hostname: str('hostname') || str('node_name') || 'unknown' });
    case 'NODE_LOST':
      return t('audit.event.node_lost');
    case 'NODE_STALE':
      return t('audit.event.node_stale');
    case 'NODE_RECONNECTED':
      return t('audit.event.node_reconnected');
    case 'RESTART_SERVICE':
    case 'START_SERVICE':
    case 'STOP_SERVICE': {
      const serviceName = str('service') || str('target');
      const res = str('result') || 'success';
      let key = 'audit.event.service_restart';
      if (action === 'START_SERVICE') key = 'audit.event.service_start';
      else if (action === 'STOP_SERVICE') key = 'audit.event.service_stop';
      return t(key, { service: serviceName, result: res });
    }
    case 'RESTART_CONTAINER':
    case 'START_CONTAINER':
    case 'STOP_CONTAINER':
    case 'CONTAINER_RESTART': {
      const containerName = str('container') || str('target');
      const res = str('result') || 'success';
      let key = 'audit.event.container_restart';
      if (action === 'START_CONTAINER') key = 'audit.event.container_start';
      else if (action === 'STOP_CONTAINER') key = 'audit.event.container_stop';
      return t(key, { container: containerName, result: res });
    }
    case 'GENERATE_JOIN_TOKEN':
      return t('audit.event.generate_token', { node_name: str('node_name') || 'unknown' });
    case 'REVOKE_NODE':
    case 'NODE_REVOKE':
      return str('reason')
        ? t('audit.event.revoke_node', { reason: str('reason') })
        : t('audit.event.revoke_node_simple');
    case 'SYSTEM_INIT':
      return t('audit.event.system_init', { message: str('message') || 'System initialized' });
    case 'UPDATE_CONFIG':
    case 'UPDATE_LLM_SETTINGS':
    case 'UPDATE_INTENT_CONFIG':
      return t('audit.event.update_config', { setting: str('setting') || 'configuration' });
    default:
      if (Object.keys(details).length > 0) {
        const detailsStr = Object.entries(details).map(([k, v]) => `${k}: ${String(v)}`).join(', ');
        return `${entry.action.replace(/_/g, ' ')} (${detailsStr})`;
      }
      return entry.action.replace(/_/g, ' ');
  }
}
