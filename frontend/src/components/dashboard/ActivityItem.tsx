import React from 'react';
import { TimeAgo } from '../primitives/TimeAgo';
import { useLocale } from '../../i18n';
import { formatAuditText } from '../../utils/formatAudit';
import {
  Terminal,
  Settings,
  LogIn,
  LogOut,
  Server,
  HelpCircle,
  Wifi,
  WifiOff,
  AlertTriangle,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  KeyRound,
  FileCode
} from 'lucide-react';

interface ActivityItemProps {
  action: string;
  actor: string;
  userId?: string;
  timestamp: string;
  details?: any;
  nodeId?: string | null;
}

export const ActivityItem: React.FC<ActivityItemProps> = ({
  action,
  actor,
  userId,
  timestamp,
  details,
  nodeId,
}) => {
  const actUpper = action.toUpperCase();

  const getActionIcon = () => {
    switch (actUpper) {
      case 'USER_LOGIN':
        return <LogIn className="w-3.5 h-3.5 text-severity-ok" />;
      case 'USER_LOGOUT':
        return <LogOut className="w-3.5 h-3.5 text-text-3" />;
      case 'USER_CHANGE_PASSWORD':
        return <KeyRound className="w-3.5 h-3.5 text-severity-info" />;
      case 'REFRESH_THEFT_DETECTED':
        return <AlertTriangle className="w-3.5 h-3.5 text-severity-critical animate-bounce" />;
      case 'PROPOSAL_APPROVED':
        return <CheckCircle2 className="w-3.5 h-3.5 text-severity-ok" />;
      case 'PROPOSAL_REJECTED':
        return <XCircle className="w-3.5 h-3.5 text-severity-critical" />;
      case 'GENERATE_JOIN_TOKEN':
        return <KeyRound className="w-3.5 h-3.5 text-severity-info" />;
      case 'REVOKE_NODE':
        return <Server className="w-3.5 h-3.5 text-severity-critical" />;
      case 'NODE_ENROLLED':
        return <ShieldCheck className="w-3.5 h-3.5 text-severity-ok" />;
      case 'NODE_RECONNECTED':
        return <Wifi className="w-3.5 h-3.5 text-severity-ok" />;
      case 'NODE_LOST':
        return <WifiOff className="w-3.5 h-3.5 text-severity-critical animate-pulse" />;
      case 'NODE_STALE':
        return <AlertTriangle className="w-3.5 h-3.5 text-severity-warning" />;
      case 'RESTART_SERVICE':
      case 'START_SERVICE':
      case 'STOP_SERVICE':
        return <Settings className="w-3.5 h-3.5 text-severity-warning" />;
      case 'RESTART_CONTAINER':
      case 'START_CONTAINER':
      case 'STOP_CONTAINER':
        return <Terminal className="w-3.5 h-3.5 text-severity-info" />;
      case 'UPLOAD_PLUGIN':
      case 'CONFIGURE_PLUGIN':
      case 'TOGGLE_PLUGIN':
      case 'DELETE_PLUGIN':
        return <FileCode className="w-3.5 h-3.5 text-accent" />;
      default:
        // Legacy fallback
        if (actUpper.includes('LOGIN')) return <LogIn className="w-3.5 h-3.5 text-accent" />;
        if (actUpper.includes('LOGOUT')) return <LogOut className="w-3.5 h-3.5 text-text-3" />;
        if (actUpper.includes('CONTAINER')) return <Terminal className="w-3.5 h-3.5 text-severity-info" />;
        if (actUpper.includes('SERVICE')) return <Settings className="w-3.5 h-3.5 text-severity-warning" />;
        return <HelpCircle className="w-3.5 h-3.5 text-text-3" />;
    }
  };

  const getCleanActionLabel = () => {
    switch (actUpper) {
      case 'USER_LOGIN':
        return 'Connexion';
      case 'USER_LOGOUT':
        return 'Déconnexion';
      case 'USER_CHANGE_PASSWORD':
        return 'MDP Modifié';
      case 'REFRESH_THEFT_DETECTED':
        return 'Vol de Token détecté';
      case 'PROPOSAL_APPROVED':
        return 'Proposition acceptée';
      case 'PROPOSAL_REJECTED':
        return 'Proposition rejetée';
      case 'GENERATE_JOIN_TOKEN':
        return 'Token d\'enrôlement';
      case 'REVOKE_NODE':
        return 'Serveur révoqué';
      case 'NODE_ENROLLED':
        return 'Nouveau serveur enrôlé';
      case 'NODE_RECONNECTED':
        return 'Serveur reconnecté';
      case 'NODE_LOST':
        return 'Serveur HORS-LIGNE';
      case 'NODE_STALE':
        return 'Serveur inactif (Stale)';
      case 'RESTART_SERVICE':
        return 'Service redémarré';
      case 'STOP_SERVICE':
        return 'Service stoppé';
      case 'START_SERVICE':
        return 'Service démarré';
      case 'RESTART_CONTAINER':
        return 'Conteneur redémarré';
      case 'STOP_CONTAINER':
        return 'Conteneur stoppé';
      case 'START_CONTAINER':
        return 'Conteneur démarré';
      case 'UPLOAD_PLUGIN':
        return 'Plugin téléversé';
      case 'CONFIGURE_PLUGIN':
        return 'Plugin configuré';
      case 'TOGGLE_PLUGIN':
        return 'Plugin activé/désactivé';
      case 'DELETE_PLUGIN':
        return 'Plugin supprimé';
      default:
        // formatting fallback
        return action.replace(/_/g, ' ');
    }
  };



  const { t } = useLocale();
  const friendlyText = formatAuditText(
    { action, actor, user_id: userId || actor, details },
    t
  );

  return (
    <div className="py-3 px-5 flex items-start justify-between gap-3 text-xs hover:bg-surface-2/30 transition-colors duration-150">
      <div className="flex items-start gap-3 min-w-0 flex-1">
        <div className="w-8 h-8 rounded-lg bg-surface-2 border border-border flex items-center justify-center shrink-0 mt-0.5">
          {getActionIcon()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-bold text-text-1">
              {getCleanActionLabel()}
            </span>
            <span className="text-text-3 text-[10px]">
              par {actor || 'système'}
            </span>
            {nodeId && (
              <span
                className="inline-block text-[8.5px] font-bold tracking-wide uppercase bg-surface-3 px-1.5 py-0.5 rounded border border-border text-text-3 font-interface"
                title={nodeId}
              >
                Node: {nodeId.substring(0, 8)}…
              </span>
            )}
          </div>
          <p className="text-text-2 text-xs font-normal mt-1 leading-normal" title={friendlyText}>
            {friendlyText}
          </p>
        </div>
      </div>
      <div className="shrink-0 text-right mt-0.5">
        <TimeAgo timestamp={timestamp} className="text-text-3 text-[10px] font-medium" />
      </div>
    </div>
  );
};
