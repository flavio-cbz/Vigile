import React, { useEffect, useRef } from 'react';

/**
 * Paire de revision S4 `(boot_id, counter)` (plan §2.2.4, contrat §8-S4).
 * `boot_id` est un UUID régénéré au démarrage du master (faille 7) ; un
 * mismatch de `boot_id` signifie un restart master → invalidation complète.
 */
export interface PluginRevision {
  boot_id: string;
  counter: number;
}

export interface MountGateProps {
  /** Paire de revision S4, injectée par le parent (source SSE en J4, T26). */
  revision: PluginRevision | null;
  /** Revision précédemment montée (état/cache du parent). */
  mountedRevision: PluginRevision | null;
  /**
   * Appelé quand la gate décide que le sous-arbre doit être rechargé
   * intégralement (mismatch de boot_id → drop des caches, remontage).
   */
  onReset?: () => void;
  /** Appelé sur un changement de counter seul (rafraîchissement partiel). */
  onRefresh?: () => void;
  children: React.ReactNode;
}

/**
 * Mount gate + load barrier clés sur la revision S4 (contrat §8-S4, tâche
 * J3b-T21). Machine à états purement présentative — aucun fetch, aucun accès
 * store ; la mémorisation de la revision montée appartient au parent qui
 * pilote `mountedRevision` depuis son état/cache :
 *
 * - `revision == null` (source non câblée, J4) → **passage direct**, jamais
 *   de blocage : les enfants sont rendus tels quels ;
 * - premier montage (`mountedRevision == null`) → rendu des enfants ;
 * - mismatch de `boot_id` → **LOAD BARRIER** : les enfants ne sont PAS rendus,
 *   placeholder de rechargement intégral affiché, `onReset()` appelé
 *   (invalidation complète + reload intégral, jamais de réconciliation
 *   partielle) ;
 * - mismatch de `counter` seul → **MOUNT GATE** : les enfants restent montés
 *   (un changement de counter est un rafraîchissement partiel, pas un
 *   remontage), `onRefresh()` appelé ;
 * - sinon → rendu des enfants inchangé.
 */
export const MountGate: React.FC<MountGateProps> = ({
  revision,
  mountedRevision,
  onReset,
  onRefresh,
  children,
}) => {
  // Refs stables : un callback inline du parent ne re-déclenche pas l'effet.
  const onResetRef = useRef(onReset);
  const onRefreshRef = useRef(onRefresh);

  useEffect(() => {
    onResetRef.current = onReset;
    onRefreshRef.current = onRefresh;
  });

  const loadBarrier =
    revision !== null &&
    mountedRevision !== null &&
    revision.boot_id !== mountedRevision.boot_id;
  const partialRefresh =
    !loadBarrier &&
    revision !== null &&
    mountedRevision !== null &&
    revision.counter !== mountedRevision.counter;

  // Clé de paire : l'effet ne se déclenche qu'au changement réel de la paire,
  // jamais sur l'identité d'objets fraîchement créés par le parent.
  const pairKey = [
    revision?.boot_id ?? '-',
    revision?.counter ?? '-',
    mountedRevision?.boot_id ?? '-',
    mountedRevision?.counter ?? '-',
  ].join(':');

  useEffect(() => {
    if (loadBarrier) {
      onResetRef.current?.();
    } else if (partialRefresh) {
      onRefreshRef.current?.();
    }
  }, [pairKey, loadBarrier, partialRefresh]);

  if (revision === null || mountedRevision === null) {
    return <>{children}</>;
  }

  if (loadBarrier) {
    return (
      <div
        data-testid="mount-gate-reloading"
        role="status"
        aria-label="Rechargement du plugin"
        className="flex items-center justify-center py-8"
      >
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-orange-500 border-zinc-800" />
      </div>
    );
  }

  return <>{children}</>;
};
