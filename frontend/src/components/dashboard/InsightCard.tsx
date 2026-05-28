import React from 'react';
import { AlertCircle, AlertTriangle, Info, CheckCircle, Sparkles } from 'lucide-react';
import { useLocale } from '../../i18n';
import { useLayoutStore } from '../../store/layoutStore';
import { useChatStore } from '../../store/chatStore';

export interface Insight {
  type: 'cpu' | 'ram' | 'disk' | 'status';
  severity: 'ok' | 'info' | 'warning' | 'critical';
  icon: string;
  headline: string;
  detail: string;
  raw?: any;
}

interface InsightCardProps {
  nodeId: string;
  nodeName: string;
  insight: Insight;
}

export const InsightCard: React.FC<InsightCardProps> = ({
  nodeId,
  nodeName,
  insight,
}) => {
  const { t } = useLocale();
  const setCopilotOpen = useLayoutStore((s) => s.setCopilotOpen);
  const { createSession, sendMessage } = useChatStore();

  const handleAnalyze = async () => {
    // Open CopilotPanel
    setCopilotOpen(true);
    
    // Compose context message
    const promptMsg = `Analyse le serveur ${nodeName} (${insight.type.toUpperCase()}) : "${insight.headline} - ${insight.detail}". Propose des pistes de remédiation.`;
    
    // Create session and send prompt
    await createSession(nodeId, `Diag: ${nodeName}`);
    sendMessage(promptMsg, nodeId);
  };

  const getSeverityColor = () => {
    switch (insight.severity) {
      case 'critical':
        return {
          border: 'border-danger/30',
          bg: 'bg-danger-subtle',
          iconColor: 'text-danger',
          iconEl: <AlertCircle size={18} />
        };
      case 'warning':
        return {
          border: 'border-warning/30',
          bg: 'bg-warning-subtle',
          iconColor: 'text-warning',
          iconEl: <AlertTriangle size={18} />
        };
      case 'info':
        return {
          border: 'border-accent-primary/20',
          bg: 'bg-accent-subtle',
          iconColor: 'text-accent-primary',
          iconEl: <Info size={18} />
        };
      default:
        return {
          border: 'border-success/20',
          bg: 'bg-success-subtle',
          iconColor: 'text-success',
          iconEl: <CheckCircle size={18} />
        };
    }
  };

  const style = getSeverityColor();

  return (
    <div className={`w-[290px] min-h-[140px] bg-surface-0 border ${style.border} rounded-xl p-4 flex flex-col justify-between hover:scale-[1.02] transition-all duration-200 shadow-sm animate-fade-in`}>
      {/* Top Header */}
      <div className="flex items-start gap-2.5">
        <div className={`shrink-0 mt-0.5 ${style.iconColor}`}>
          {style.iconEl}
        </div>
        <div className="min-w-0">
          <h4 className="text-xs font-bold text-ink-primary leading-tight">
            {insight.headline}
          </h4>
          <span className="text-[9px] text-ink-muted font-mono uppercase mt-0.5 block">
            {nodeName} · {insight.type}
          </span>
        </div>
      </div>

      {/* Details Description */}
      <p className="text-[11px] text-ink-secondary my-2 leading-relaxed line-clamp-2">
        {insight.detail}
      </p>

      {/* IA Analysis Trigger CTA */}
      <div className="border-t border-border/40 pt-2 flex items-center justify-between mt-auto">
        <span className="text-[9px] text-ink-muted">
          Vigil Insights
        </span>
        <button
          onClick={handleAnalyze}
          className="text-[10px] font-semibold text-accent-primary hover:text-accent-hover flex items-center gap-1 cursor-pointer bg-transparent border-none p-0"
        >
          <Sparkles size={10} className="text-accent-primary" />
          {t('card.analyze_ai')}
        </button>
      </div>
    </div>
  );
};
