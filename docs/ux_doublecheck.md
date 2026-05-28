# Rapport de Double-Check UX — Vigile

> Chaque point de l'audit initial a été confronté au code source réel.
>
> **27 fichiers lus** : Dashboard.tsx (1021L), NodeDetail.tsx (983L), Chat.tsx (699L),
> Proposals.tsx (482L), Audit.tsx (447L), Plugins.tsx (993L), Settings.tsx (703L),
> Login.tsx (599L), Sidebar.tsx (472L), TopBar.tsx (204L), RootLayout.tsx (59L),
> CopilotPanel.tsx (432L), AddNodeModal.tsx (179L), ProposalModal.tsx (252L),
> VigilInsights.tsx (665L), HealthBanner.tsx (132L), UptimeTracker.tsx (281L),
> VigileEye.tsx (247L), ToastContainer.tsx (94L), CommandPalette.tsx (168L),
> EmptyState.tsx (53L), nodeStore.ts (122L), authStore.ts (66L),
> layoutStore.ts (43L), useToastStore.ts (58L), useApi.ts (61L),
> usePolling.ts (45L), index.css (172L)
>
> **6 fichiers backend** : chat.py (système de prompts), structured_llm.py,
> insights.py (prompts profil + diagnostic), llm_client.py

---

## Points confirmés (diagnostic inchangé après vérification)

### ✅ 1. La bannière d'alerte globale ne montre pas les noms des serveurs en panne

[HealthBanner.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/components/ui/HealthBanner.tsx) affiche
uniquement des compteurs : `"X serveur(s) hors-ligne"` (L80). Aucune prop ni logique
pour afficher les noms des nœuds concernés. L'utilisateur doit parcourir les cartes
ou la sidebar pour identifier lequel est tombé.

**Impact** : Critique à 23h sur mobile — "1 serveur hors-ligne" sans dire lequel.

---

### ✅ 2. Le fossé linguistique de l'IA — confirmé et aggravé

Le problème est **systémique**. Aucun des prompts LLM ne spécifie de langue de réponse :

| Fichier backend | Lignes | Langue spécifiée ? |
|---|---|---|
| [chat.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/api/chat.py) L699-757 | Prompt système chat (3 variantes) | ❌ Non |
| [chat.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/api/chat.py) L783-787 | Prompt extraction de propositions | ❌ Non |
| [structured_llm.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/core/structured_llm.py) L73-78 | Prompt JSON structuré | ❌ Non |
| [insights.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/core/insights.py) L143-155 | Prompt profil serveur | ❌ Non |
| [insights.py](file:///f:/Youcloud/Documents/Projets/Youcloud-API/master/core/insights.py) L632-643 | Prompt diagnostic anomalie | ❌ Non |

Les strings rule-based dans `insights.py` sont en français (ex: *"Disque plein dans moins d'un jour !"*),
mais les sorties LLM sont en anglais par défaut. Résultat visible sur les screenshots :
le raisonnement de l'IA dit *"High memory usage detected on web-app container"*
dans une interface 100% française.

Côté frontend, des chaînes anglaises parasites existent aussi :

| Fichier | Exemple |
|---|---|
| [Proposals.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Proposals.tsx) L399 | `"CONSOLE TERMINAL OUTPUT"` |
| [NodeDetail.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) L914 | `"Bash Console logs"` |
| [Login.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Login.tsx) L383-420 | `"Zero-Trust Autonomous Fleet Operations"`, `"CHAIN SECURED"` |
| [Plugins.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Plugins.tsx) L45-51, L552 | Catégories en anglais, badge `"Stale"` |

---

### ✅ 3. Absence de vision "Applications/Conteneurs" sur le Dashboard

Les cartes serveur du Dashboard affichent : nom, hostname, OS/Arch, CPU%, RAM%, Disk%, Uptime.
**Aucun conteneur Docker n'est listé.** Pour voir les conteneurs, il faut naviguer vers
[NodeDetail.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) → onglet Containers.

L'utilisateur ne sait pas que Plex est tombé en regardant le Dashboard —
il voit juste des métriques globales du serveur.

---

### ✅ 4. Trop d'étapes pour le parcours "quelque chose cloche → j'agis"

Le chemin actuel pour redémarrer un conteneur :

**Via l'interface directe** (3-4 taps) :
1. Dashboard → cliquer carte serveur → NodeDetail
2. Onglet "Containers"
3. Trouver le conteneur dans la table
4. Cliquer "Redémarrer" (admin only)

**Via l'IA** (3-5 taps) :
1. Dashboard → "Analyser avec l'IA" ou Chat IA
2. Attendre la réponse
3. Aller sur Propositions (ou voir inline dans le chat)
4. Approuver

---

### ✅ 5. Le style "Glass Dark Ops" crée du bruit visuel (nuancé)

[index.css](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/index.css) :
- L89-98 : Grain texture SVG overlay à `z-9999`, opacity 0.028
- L100-111 : `.glass-panel` avec `backdrop-filter: blur(12px)`
- L130-162 : `.cyber-corners` — pseudo-éléments pour coins HUD

**Cependant**, les contrastes de texte sont **bien calibrés** : `--color-ink: #ede7de`
(off-white chaud) sur `--color-bg: #050505` donne un excellent ratio. Le problème
n'est pas le contraste mais les **éléments décoratifs** qui distraient.

---

## Points corrigés (je m'étais trompé ou j'avais supposé)

### ❌→✅ 1. "L'interface cache les métriques de base"

**J'avais tort.** Les métriques brutes CPU/RAM/Disk% EXISTENT et sont affichées :

- **Single-server mode** : Carte "Ressources en Direct" ([Dashboard.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Dashboard.tsx) L720-770)
  avec barres de progression + pourcentages + seuils colorés
- **Multi-server mode** : Chaque carte serveur (L882-996) affiche CPU/RAM/Disk%
- **VigilInsights mode avancé** : Sparklines Recharts + valeurs brutes
- **Section "Métriques Brutes"** (L632-999) : panneau complet caché par défaut

La philosophie **insights narratifs en priorité, métriques brutes en secondaire**
est un choix de design intentionnel et cohérent avec le brief produit.

---

### ❌→✅ 2. "L'utilisateur n'a aucun moyen d'exécuter une action directement"

**Partiellement tort.** [NodeDetail.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) offre :
- Bouton "Redémarrer" par service systemd (L701-713, admin only)
- Bouton "Redémarrer" par conteneur Docker (L800-811, admin only)
- Bouton de révocation serveur (L387-395)

Le problème n'est pas l'absence mais l'**accessibilité** :
ces contrôles ne sont disponibles que dans NodeDetail, jamais depuis le Dashboard.

---

### ❌→✅ 3. "Contradiction sidebar Connecté vs bannière hors-ligne"

**Nuancé.** La sidebar et la bannière lisent la même source (`nodeStore.nodes[].online`).
La sidebar affiche correctement un dot muted + "hors ligne" quand `srv.online === false`
(L82-84 et L214-224). Le screenshot de l'audit montrait un état transitoire —
les deux composants ne se rafraîchissent pas au même moment (polling 60s).

C'est un problème de **fraîcheur de données**, pas un bug de logique UI.

---

## Angles morts comblés (nouveaux problèmes trouvés)

### 🔴 1. Feedback post-action : `alert()` natif partout sauf Settings (CRITIQUE)

C'est le problème UX le plus grave non identifié dans l'audit initial.

| Page | Méthode de feedback | Qualité |
|---|---|---|
| [Proposals.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Proposals.tsx) L99, L101, L106, L130, L138 | `alert()` natif | ❌ Bloquant |
| [Chat.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Chat.tsx) L374 | `alert()` natif | ❌ Bloquant |
| [NodeDetail.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx) L252-311 | `alert()` natif (8 occurrences) | ❌ Bloquant |
| [Settings.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Settings.tsx) | Toast store | ✅ Propre |
| [Plugins.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Plugins.tsx) | Bannières inline | ✅ Propre |
| [Audit.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Audit.tsx) | Bannières inline | ✅ Propre |

> [!CAUTION]
> Un toast store existe ([useToastStore.ts](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/store/useToastStore.ts))
> et un [ToastContainer.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/components/ui/ToastContainer.tsx)
> est monté dans le RootLayout. **Seul Settings.tsx l'utilise.**
> Les 3 pages les plus critiques (Proposals, NodeDetail, Chat) utilisent `window.alert()`.

---

### 🔴 2. Login : le succès de changement de mot de passe s'affiche comme une erreur

[Login.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Login.tsx) L359 :
`setError("Mot de passe mis à jour. Veuillez vous connecter à nouveau.")` —
l'état d'erreur est réutilisé pour un message positif. L'utilisateur voit un message
de succès dans un bandeau rouge.

---

### 🟡 3. Flux de rejet incohérent entre Chat et Proposals

- **Proposals.tsx** : "Refuser" → modal avec textarea obligatoire pour la raison
- **Chat.tsx** (L344-376) : rejet immédiat sans raison, sans confirmation
- **CopilotPanel.tsx** : même comportement que Chat — rejet sans raison

L'utilisateur peut rejeter la même proposition de façons totalement différentes
selon le contexte d'où il le fait.

---

### 🟡 4. CopilotPanel — 3 points d'entrée IA sans état partagé

L'utilisateur a **3 endroits** pour parler à l'IA :

| Entrée | Fichier | Persisté ? | État partagé ? |
|---|---|---|---|
| Page Chat (`/chat/:id`) | [Chat.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/pages/Chat.tsx) | ✅ Oui (sessions backend) | Non |
| CopilotPanel (side panel) | [CopilotPanel.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/components/copilot/CopilotPanel.tsx) | ❌ Non (local state) | Non |
| "Analyser avec l'IA" (VigilInsights) | [VigilInsights.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/components/ui/VigilInsights.tsx) | ❌ Non (modal one-shot) | Non |

Ces 3 flux ne partagent aucun état. Une conversation CopilotPanel est invisible
sur la page Chat et vice-versa.

---

### 🟡 5. Onboarding Worker — aucun feedback de progression et risque de fuite mémoire

[AddNodeModal.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/components/modals/AddNodeModal.tsx) :
après génération du token + commande curl, le modal ne montre aucun feedback :
- Pas de "En attente de connexion..."
- Pas de notification quand le serveur s'enrôle
- L'utilisateur doit fermer le modal et attendre le prochain poll (60s)

> [!WARNING]
> Pour résoudre cela en ajoutant un polling toutes les 5s, il faut absolument intégrer un `clearInterval` dans le cleanup du `useEffect` (lors du démontage/fermeture du modal) afin d'éviter une fuite de mémoire côté client si l'utilisateur ferme la modale avant la fin de la connexion.

---

### 🟡 6. VigilInsights vide = trou dans la page

[VigilInsights.tsx](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/components/ui/VigilInsights.tsx) :
quand il n'y a pas de données (aucun nœud en ligne ou API vide), le composant fait
`return null` — le bloc disparaît sans aucun message explicatif.

---

### 🟡 7. Scaling CSS contradictoire

- [index.css](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/index.css) L72 : `html { font-size: 90%; }`
- [layoutStore.ts](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/store/layoutStore.ts) L4-6 : force `fontSize = '125%'` en JS

Le JS gagne (inline style > stylesheet). La déclaration CSS est morte.
Toute l'échelle `rem` Tailwind est calibrée sur 125% × 16px = **20px de base**,
ce qui rend tous les spacings 25% plus grands que les valeurs attendues.

---

### 🟡 8. `usePolling` hook existe mais n'est importé nulle part

[usePolling.ts](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/hooks/usePolling.ts) implémente un registre
partagé avec gestion de souscripteurs. **Aucun composant ne l'importe.**
Le polling est fait à la main avec `setInterval` dans Dashboard (60s),
UptimeTracker (30s), RootLayout (60s).

---

### 🟡 9. App.css est un fichier mort

[App.css](file:///f:/Youcloud/Documents/Projets/Youcloud-API/frontend/src/App.css) (185 lignes)
contient du CSS boilerplate Vite/Tauri (`.hero`, `.counter`, `#next-steps`).
Aucun composant ne l'utilise.

---

### 🟡 10. Plugins.tsx utilise `window.confirm()` pour la suppression

Incohérent avec le pattern de modal de confirmation utilisé dans NodeDetail
et Proposals.

---

## Points retirés (en contradiction avec les contraintes du projet)

### ❌ 1. "Supprimer la page Audit"
Page d'administration avec vérification d'intégrité SHA256. Fondamentale pour le
modèle de sécurité. À **reléguer** hors de la nav principale, pas à supprimer.

### ❌ 2. "Supprimer la page Plugins"
Page admin pour le Sprint 5 (écosystème plugins). À reléguer, pas supprimer.

### ❌ 3. "Les insights ne donnent pas plus qu'un simple état vert/rouge"
J'avais sous-estimé la valeur. *"Disque plein dans 1 semaine et 3j"* est objectivement
plus utile qu'un badge "Warning 80%". La projection temporelle est un vrai avantage produit.

### ❌ 4. "Refonte complète du design system Glass Dark Ops"
Disproportionné. Les contrastes sont bons. Seuls les éléments décoratifs spécifiques
(grain, cyber-corners, double scaling) sont à nettoyer.
