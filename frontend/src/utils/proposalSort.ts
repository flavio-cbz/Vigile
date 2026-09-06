import type { ActionProposal } from '../store/uiStore';

/**
 * Tri prioritaire frontend pour les propositions d'actions.
 * Ordre : CRITICAL (5) > HIGH (4) > MEDIUM = WARNING (3) > LOW (2) > OK (1) > unknown (0)
 * Puis date décroissante (max(created_at, updated_at)).
 */

const RISK_SCORE: Record<string, number> = {
  critical: 5,
  high: 4,
  medium: 3,
  warning: 3,
  low: 2,
  ok: 1,
};

export function getRiskScore(risk: string | undefined | null): number {
  if (!risk) return 0;
  return RISK_SCORE[risk.toLowerCase()] ?? 0;
}

export function getProposalDate(p: Pick<ActionProposal, 'created_at' | 'updated_at'>): number {
  const c = typeof p.created_at === 'number' && !isNaN(p.created_at) && p.created_at > 0 ? p.created_at : 0;
  const u = typeof p.updated_at === 'number' && !isNaN(p.updated_at) && p.updated_at > 0 ? p.updated_at : 0;
  if (!u) return c;
  if (!c) return u;
  return Math.max(c, u);
}

export function sortProposalsByRiskAndDate<T extends ActionProposal>(proposals: T[]): T[] {
  return [...proposals].sort((a, b) => {
    const ra = getRiskScore(a.risk_level);
    const rb = getRiskScore(b.risk_level);
    if (rb !== ra) return rb - ra;
    const da = getProposalDate(a);
    const db = getProposalDate(b);
    return db - da;
  });
}
