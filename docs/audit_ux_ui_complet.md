# Audit UX/UI Complet – Tableau de Bord Vigile

Ce document rassemble l'intégralité des problèmes ergonomiques, visuels et d'accessibilité identifiés lors de l'audit du tableau de bord Vigile.

---

## 1. Architecture de l'Information et Disposition Générale

**Verdict Global :** ⚠️ REFONTE PARTIELLE
L'architecture globale et la disposition du tableau de bord sont logiques (utilisation standard d'une barre latérale et placement des indicateurs clés au-dessus de la ligne de flottaison).

- **Problème :** La barre d'action supérieure nécessite une restructuration en raison de la concurrence entre plusieurs appels à l'action ("Actualiser", "Nouvelle Conversation", "Ajouter un serveur").
- **Impact :** Cette disposition viole la règle d'un seul bouton principal par vue, dilue la hiérarchie visuelle et disperse l'attention de l'utilisateur.
- **Correction :** Consolider cette section pour mettre en évidence un seul bouton d'appel à l'action (CTA) primaire clair, tout en rétrogradant les autres vers des styles visuels secondaires (ex: boutons fantômes).

---

## 2. Gestion Multi-Serveurs

**Verdict Global :** 🔴 REFONTE COMPLÈTE NÉCESSAIRE
Bien que le sélecteur de contexte de la barre latérale et les métriques globales fournissent une base, le flux de gestion multi-serveurs échoue fondamentalement en matière de scalabilité et de comparaison.

**Benchmark :** Des outils comme **Portainer** (vue en grille avec colonnes triables et indicateurs de santé) et **Datadog** (menus déroulants de contexte scalables avec recherche et listes d'infrastructure dédiées) gèrent cela de manière exceptionnelle.

### Problèmes identifiés :

- **[Critique] Pas de vue liste/grille des serveurs :**
  - **Impact :** Les utilisateurs sont contraints de naviguer de manière fastidieuse via le menu déroulant pour voir l'état individuel de chaque serveur.
  - **Correction :** Implémenter un tableau ou une grille "Serveurs" sur le tableau de bord global affichant le nom, le statut visuel et les métriques rapides (CPU/RAM) de chaque serveur.
- **[Critique] Sélecteur de contexte non scalable (absence de recherche) :**
  - **Impact :** L'interface ne passe pas à l'échelle ; avec 10 serveurs ou plus, l'utilisateur devra faire défiler une longue liste pour trouver une instance spécifique.
  - **Correction :** Introduire une barre de recherche "sticky" en haut du menu déroulant pour filtrer facilement par nom.
- **[Majeur] Statut des serveurs au format texte uniquement :**
  - **Impact :** Les statuts purement textuels (ex: "test-api-node hors ligne") empêchent un balayage visuel rapide, augmentant la charge cognitive.
  - **Correction :** Remplacer ou compléter le texte par des indicateurs visuels clairs (ex: pastilles 🔴 rouge / 🟢 verte) alignés à côté du nom.
- **[Mineur] Libellé du contexte actif encombré :**
  - **Impact :** Le nom de l'entité et son statut sont fusionnés (ex: "Tous les serveurs 0 en ligne"), ce qui rend la lecture maladroite.
  - **Correction :** Séparer le nom de l'entité de son statut en affichant ce dernier sous forme de badge visuel distinct.
- **[Mineur] Incohérence de l'action d'ajout de serveur :**
  - **Impact :** Le placement double et la terminologie incohérente ("Ajouter un serveur" vs "Enrôler un serveur") créent de la confusion.
  - **Correction :** Standardiser la formulation ("Ajouter un serveur") et positionner l'action principale clairement dans la nouvelle vue liste.

---

## 3. Audit Spécifique des Composants (Composants, UI, Accessibilité)

### Problèmes Critiques
- **Cartes de plugins non sémantiques :** Les cartes interactives (ex: "Metrics Collector") sont de simples `<div>`. Les utilisateurs au clavier et les lecteurs d'écran ne peuvent ni les cibler ni interagir avec, bloquant l'accès à la configuration.
  - *Correction :* Utiliser des balises sémantiques `<button>` ou `<a>`, ou ajouter `role="button"` et `tabindex="0"`.
- **Badge "PANIQUE" illisible :** Le badge dans la carte VIGILBOT utilise un texte rouge foncé sur fond rouge foncé, ce qui le rend illisible.
  - *Correction :* Utiliser un texte blanc sur un fond rouge vif.
- **État vide "Tâches récentes" cassé :** Une grande boîte sombre vide apparaît avec un chevron flottant, et le texte est poussé hors de vue. Cela ressemble à un bug d'affichage.
  - *Correction :* Centrer correctement l'illustration et le texte, et masquer les chevrons de navigation.
- **Contraste du statut serveur ("0 en ligne") :** Dans la barre latérale, le texte est gris foncé sur un fond sombre.
  - *Correction :* Éclaircir le texte pour respecter les normes de contraste WCAG.
- **Badge de version du système illisible :** Le tag "VIGILE AI CORE V0.2.0" utilise du gris foncé sur fond noir/gris très foncé.
  - *Correction :* Éclaircir la couleur du texte ou du fond du badge.

### Problèmes Majeurs
- **Boutons icônes non accessibles :** Les flèches de carrousel et le bouton de fermeture de l'IA Copilot n'ont ni texte, ni attributs `aria-label`.
  - *Correction :* Ajouter des attributs `aria-label` descriptifs.
- **Flèches de navigation visibles sur les états vides :** Afficher des flèches sans contenu à faire défiler donne l'impression d'un contenu masqué ou cassé.
  - *Correction :* Masquer les boutons de carrousel lorsque la liste est vide.
- **Manque de hiérarchie des boutons d'en-tête :** "Actualiser" et "Ajouter un serveur" ont le même style de bordure discrète, sans bouton principal évident.
  - *Correction :* Donner une couleur de fond pleine à l'action principale ("Ajouter un serveur").
- **Profil utilisateur dupliqué :** Affiché en bas de la barre latérale ET en haut à droite.
  - *Correction :* Supprimer l'un des blocs de profil.
- **Bouton "Nouvelle Conversation" peu contrasté :** Texte bleu canard sur fond bleu canard foncé, très peu lisible.
  - *Correction :* Augmenter le contraste avec du texte blanc ou un bleu nettement plus clair.
- **Barres de progression invisibles à 0% :** Les pistes des barres (carte UTILISATION MOYENNE) sont si sombres qu'elles disparaissent, laissant les pourcentages flotter dans le vide.
  - *Correction :* Éclaircir légèrement la couleur de la piste de progression à vide.

### Problèmes Mineurs
- **États vides (Empty states) bruts :** Les textes comme "Aucune tâche récente" flottent sans conteneur visuel délimité, paraissant non finalisés.
  - *Correction :* Encapsuler dans un composant stylisé (carte avec bordure pointillée, fond atténué, icône).
- **Points d'entrée "Nouvelle Conversation" redondants :** Plusieurs liens et boutons éparpillés font double emploi avec le panneau permanent "Copilot IA".
  - *Correction :* Standardiser autour du panneau Copilot et supprimer les autres liens.
- **Émojis peu professionnels (🧐, 😰) :** Décalage de ton avec la nature sérieuse et technique de la surveillance de serveurs.
  - *Correction :* Remplacer par des icônes SVG de statut standard (avertissements, cloches, etc.).
- **Titres de sections de la barre latérale peu lisibles :** Texte gris foncé très petit sur fond noir pour "NAVIGATION" et "SERVEUR ACTIF".
  - *Correction :* Éclaircir légèrement le texte.
- **Icône de réduction `<<` peu visible :** L'icône de fermeture de la barre latérale se fond dans le décor.
  - *Correction :* Aligner le contraste de l'icône sur celui du logo "Vigile".
- **Bouton "Voir tout" flottant :** Le bouton flotte loin à droite dans "TÂCHES RÉCENTES", déconnecté de son titre.
  - *Correction :* Le rapprocher du titre ou l'enfermer dans un conteneur subtil.

---

## 4. Vision "Netflix-Style" & Layout Global

**Verdict Global :** 🔴 REFONTE COMPLÈTE NÉCESSAIRE
Le tableau de bord actuel est un mélange de widgets statiques (métriques, état global) et de carrousels partiels (Tâches récentes). Il ne respecte pas le modèle mental de la navigation horizontale par ligne ("swimlanes") et s'apparente trop à un panneau de contrôle brut plutôt qu'à une vue d'ensemble fluide et orientée contenu.

**Benchmark :**
- **Netflix / Plex / Jellyfin :** Excellent modèle mental avec des lignes horizontales homogènes, des fondus en dégradé pour indiquer le défilement ("scroll hints"), un "Hero Banner" dominant, et une structure claire par catégorie.
- **Grafana :** Modèle basé sur une grille stricte. Utile pour la densité des données, mais moins narratif et plus intimidant pour les profils non techniques. Vigile doit s'éloigner du modèle Grafana pour adopter la fluidité de Netflix.

### Analyse des écarts (Gap Analysis) :
1. **Modèle de ligne (Row model) brisé :** L'interface mélange des affichages en grille et des composants hétérogènes.
2. **Mapping Plugin-to-Section confus :** Il n'est pas visuellement clair qu'une ligne = un plugin. Les en-têtes de ligne n'ont pas de standard (icône, nom, lien "Voir tout").
3. **Aucune priorisation des lignes :** Il n'y a pas de "Hero section" pour les métriques de santé vitales (comme le "Top Pick" de Netflix). L'ordre semble statique et non modifiable par l'utilisateur.
4. **UX de défilement horizontal faible :** Les flèches de navigation sont basiques et il manque un "fade" (dégradé) aux extrémités pour suggérer du contenu supplémentaire. Le défilement au trackpad risque d'être rugueux sans une configuration CSS moderne (`scroll-snap`, `overflow-x: auto`).
5. **Problème de scalabilité (10+ plugins) :** En ajoutant plus de plugins, la page deviendra un défilement vertical interminable sans regroupement thématique clair (ex: "Monitoring Réseau", "Sécurité", "Ressources").

### Problèmes Spécifiques aux Composants (Vision Layout)

- **[Critique] Pas de structure "PluginRow" standardisée**
  - **Impact :** Chaque plugin implémente son interface différemment, détruisant la cohérence visuelle.
  - **Correction :** Créer un composant parent `PluginRow` qui gère le titre, le défilement et l'état vide pour tous les plugins.
- **[Critique] Absence de "Hero Banner"**
  - **Impact :** Aucune donnée n'attire immédiatement l'œil comme étant l'état vital du système. Le regard se disperse.
  - **Correction :** Remplacer les métriques globales actuelles par un composant Hero très visible en haut de page.
- **[Majeur] Indicateurs de défilement insuffisants (Scroll Affordances)**
  - **Impact :** Les utilisateurs peuvent ne pas réaliser qu'il y a du contenu supplémentaire à droite si la dernière carte est coupée brusquement.
  - **Correction :** Ajouter un masque en dégradé (gradient fade) sur le bord droit du carrousel et activer le `scroll-snap` natif.
- **[Mineur] Comportement des états vides (Empty Rows)**
  - **Impact :** Actuellement, les conteneurs vides prennent trop de place.
  - **Correction :** Le composant de ligne doit masquer ou minimiser la hauteur de la ligne si le plugin ne renvoie aucune donnée, ou afficher un composant de remplacement élégant (placeholder).

### Pseudocode JSX Idéal (PluginRow)

```jsx
<PluginRow title="Monitoring Réseau" icon={<NetworkIcon />} onSeeAll={() => navigate('/network')}>
  <HorizontalScrollContainer showFades={true}>
    {data.length === 0 ? (
      <EmptyState message="Aucune donnée réseau pour le moment" />
    ) : (
      data.map(item => <PluginCard key={item.id} data={item} />)
    )}
  </HorizontalScrollContainer>
</PluginRow>
```

---

## 5. Blind Spots: Loading, Errors & the 5-Second Rule

### 1. Loading States
- **What's wrong**: The app currently uses basic `<div>Chargement...</div>` text elements bound to boolean flags (`isProposalsLoading`, `isSessionsLoading`, `metric.loading`) instead of structural skeleton screens.
- **Why it matters**: When data is fetching, the layout collapses or jumps abruptly. Once the data arrives, the UI jerks again, resulting in a very jarring, unpolished experience (Layout Shifts).
- **Fix**: Implement fixed-height Skeleton components (e.g., `<CardSkeleton />`, `<RowSkeleton />`) that perfectly match the dimensions of the final loaded content so the layout remains 100% stable during network requests.
- **Severity**: Major

### 2. Error States
- **What's wrong**: Fetch errors (like failing to load chat sessions or plugin data) are silently caught and dumped via `console.error()`. There are no user-facing inline error boundaries or toast notifications. If a WebSocket drops, the user is not actively notified.
- **Why it matters**: Silent failures erode trust. If a plugin times out or the server disconnects, the user will stare at a frozen or blank dashboard, assuming there is no data rather than a technical failure.
- **Fix**: Introduce a global Toast notification system for transient network/WebSocket drops, and use inline Error Boundary components for specific plugins (e.g., replacing the plugin row with a subtle "Unable to load data" state + retry button).
- **Severity**: Critical

### 3. The 5-Second Rule
- **What's wrong**: The dashboard completely fails the 5-second rule. To understand global health, a user currently has to parse multiple scattered pieces of text: the "X en ligne" text in the sidebar, the "PANIQUE" tag in the Vigilbot card, and various numerical averages.
- **Why it matters**: In incident response, cognitive load must be zero. If a server is down, the user should know the millisecond they open the dashboard, without having to "read" anything.
- **Fix**: The single component that will fix this is a massive **Global Health Hero Banner** spanning the top of the dashboard. If everything is fine, it should be a calm, reassuring green ("All Systems Operational"). If something is broken, it immediately flips to an unmistakable bright red banner ("1 Server Offline", "Plugin API Timeout"), making the system state instantly recognizable from across the room.
- **Severity**: Critical
