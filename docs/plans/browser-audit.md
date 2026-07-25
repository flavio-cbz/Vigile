# Plan QA End-to-End — Vigile (vigile.youcloud.ovh)

> **Objectif** : Tester dans un navigateur Chrome l'intégralité des pages et fonctionnalités accessibles avec un compte administrateur, identifier tous les défauts (fonctionnels, visuels, UX, responsive, navigation, erreurs techniques), puis les corriger après validation.

---

## 0. Méthodologie de travail

Pour garantir une couverture e2e absolue, zéro amnésie de mémoire vive et des preuves irréfutables, les tests s'exécutent selon une **méthodologie rigoureuse en 2 Étapes et 3 Niveaux de Vérification** :

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        ÉTAPE 1 : RAFALE DE CAPTURES & INTERACTIONS                     │
│  • Exécution fluide et rapide sur le navigateur sans latence LLM                       │
│  • Enregistrement physique d'artefacts HD (.png) aux 3 résolutions (1440p, 768p, 375p) │
│  • Sauvegarde des dômes d'états et logs sur le disque (/artifacts/step_XX.png)         │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        ÉTAPE 2 : ANALYSE GLOBALE, LOGS & REPORTING                     │
│  • Inspection exhaustive de la totalité des preuves physiques stockées sur disque      │
│  • Cross-validation : UI visuelle ↔ Logs console ↔ Réponses JSON API ↔ Audit Hash     │
│  • Rédaction des livrables de recette, matrices de couverture et fiches d'anomalies    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 🔍 Les 3 Niveaux de Vérification "Sur le Terrain" (Ground Truth)

Pour toute action modifiant l'infrastructure (redémarrage conteneur Docker, service systemd, modification de configuration, kill/renice de processus, scan disque), la conformité est validée à **3 niveaux successifs** :

1. **Niveau 1 — Frontend UI** : Vérification visuelle immédiate (état des boutons, spinners de chargement, modales de confirmation, toasts de notification).
2. **Niveau 2 — API & Log Audit Master** : Vérification des réponses HTTP (codes status 200/403/429), payloads JSON et entrées dans la chaîne de hachage cryptographique SHA256 (`GET /api/admin/audit-verify`).
3. **Niveau 3 — Terrain SSH sur Serveurs Distants** :
   - **Oracle Server** (`flavio@youcloud.ovh` / `100.106.223.37`)
   - **Net Hunter Server** (`flavio@81.49.190.197`)
   - Validation directe en ligne de commande (`docker inspect --format='{{.State.StartedAt}}'`, `systemctl status`, `du -sb`, `ps aux`) pour confirmer le résultat réel OS/Docker.

---

## 1. Inventaire du périmètre

### 1.1 Routes / Pages détectées dans le code

| # | Route | Composant | Accès | Navigation |
|---|-------|-----------|-------|------------|
| 1 | `/login` | `LoginPage` | 🔓 Public | Page standalone |
| 2 | `/` | `Dashboard` | 🔐 Authentifié | Sidebar → Dashboard |
| 3 | `/servers` | `ServersPage` | 🔐 Authentifié | Sidebar → Servers |
| 4 | `/nodes/:id` | `NodeDetail` | 🔐 Authentifié | Clic sur un serveur |
| 5 | `/proposals` | `ProposalsPage` | 🔐 Authentifié | Sidebar → Proposals (badge) |
| 6 | `/chat/new` | `ChatRedirect` | 🔐 Authentifié | Sidebar → Copilot |
| 7 | `/automations` | `AutomationsPage` | 🔐 Admin/Operator | Sidebar Admin → Automations |
| 8 | `/plugins` | `PluginsPage` | 🔐 Admin/Operator | Sidebar Admin → Plugins |
| 9 | `/settings` | `SettingsPage` | 🔐 Authentifié | Sidebar Admin → Settings / Footer profil |
| 10 | `*` (catch-all) | `Navigate → /` | Fallback | Redirige vers `/` |

### 1.2 Sous-vues et onglets internes

#### NodeDetail (`/nodes/:id?tab=...`)
| Onglet | Composant | Contenu |
|--------|-----------|---------|
| `insights` | `NodeDetailInsightsTab` | Insights IA et système du nœud |
| `metrics` | `NodeDetailMetricsTab` | Télémétrie temps réel (CPU, RAM, Disque, Load) + graphiques |
| `services` | `NodeDetailServicesTab` | Liste services systemd + statuts |
| `containers` | `NodeDetailContainersTab` | Liste conteneurs Docker + statuts |
| `logs` | `NodeDetailLogsTab` | Viewer de logs syslog/service |
| `disk` | `NodeDetailDiskTab` | Treemap d3 style GrandPerspective + scan |
| `settings` | `NodeSettingsTab` | Configuration nœud + clé enrollment |

#### SettingsPage (`/settings`)
| Onglet | Composant | Contenu |
|--------|-----------|---------|
| `profile` | `ProfileSettingsTab` | Apparence, langue, changement de mot de passe |
| `system` → General | `GeneralSettingsTab` | Configuration générale master |
| `system` → LLM | `LLMSettingsTab` | Configuration API LLM (clé, modèle, endpoint) |
| `system` → Security | `SecuritySettingsTab` | Paramètres de sécurité |
| `system` → Plugins | `PluginsSettingsTab` | Gestion plugins dans settings |

#### PluginsPage (`/plugins`)
| Onglet | Contenu |
|--------|---------|
| `installed` | Plugins installés + modale configuration |
| `registry` | Marketplace de plugins distants |

#### ProposalsPage (`/proposals`)
| Section | Contenu |
|---------|---------|
| Operational Memory | Facts profil LLM (HITL pending/approved/rejected) |
| Action Proposals | Propositions d'actions Copilot (PENDING → APPROVED → EXECUTED/FAILED) |

### 1.3 Composants interactifs inventoriés

#### Modales
| Composant | Déclencheur | Fonction |
|-----------|-------------|----------|
| `AddNodeModal` | Bouton "Add Server" | Génère un token d'enrôlement + commande worker |
| `RenameNodeModal` | Menu kebab serveur → Rename | Renommer un nœud |
| `ConfirmDeleteModal` | Menu kebab serveur → Delete | Suppression d'un nœud (⚠️ destructif) |
| `ServerConfigModal` | Menu kebab serveur → Configure | Configuration serveur |
| `JoinTokenDisplay` | Depuis AddNodeModal | Affiche le token et les instructions d'installation |
| `EnrollmentMonitor` | Après génération token | Surveille l'enrôlement en temps réel |
| `ProposalModal` | Clic sur une proposition | Détails + Approve/Reject d'une action proposal |
| `ProposalRejectModal` | Bouton Reject dans ProposalModal | Saisie raison de rejet |
| `AllChatsModal` | Copilot → historique | Liste toutes les conversations |
| `RuleFormModal` | Automations → Create/Edit | Formulaire CRUD automation rule |
| `TestRuleModal` | Automations → Test Rule | Test d'une règle automation |
| `PluginDetailModal` | Clic plugin installé | Configuration d'un plugin |

#### Composants Dashboard
| Composant | Fonction |
|-----------|----------|
| `HeroBanner` / `HeroInsight` | Bannière hero avec insight IA principal |
| `FleetGrid` / `FleetSection` | Grille de nœuds avec statuts |
| `NodeCard` / `ServerCard` | Carte serveur avec métriques résumées |
| `InsightCard` / `InsightsSection` | Cartes d'insights IA |
| `ProposalCard` / `ProposalsSection` | Propositions en attente |
| `ContainerCard` / `ContainersSection` | Conteneurs Docker résumés |
| `ActivityItem` / `ActivitySection` | Fil d'activité récente |
| `TrendChart` / `TrendBar` | Graphiques de tendance temporelle |
| `PeriodSelector` | Sélecteur période (24h, 7d, 30d) |
| `DashboardSkeleton` | Loading state skeleton |
| `SwimLane` | Swimlane de sections scrollables |

#### Composants UI globaux
| Composant | Fonction |
|-----------|----------|
| `CommandPalette` | Palette de commandes (Cmd+K) |
| `CopilotPanel` | Panneau Copilot latéral (drawer) |
| `NotifBell` | Cloche de notifications header (proposals pending & alertes) |
| `ToastContainer` | Notifications toast avec cooldown 6s anti-flood 429 |
| `ErrorBoundary` | Boundary d'erreurs React avec bouton Retry |
| `EmptyState` | État vide générique avec CTA et icône personnalisée |
| `CardSkeleton` | Suite Skeletons (Row, Card, Banner, Chart, Proposal, Chat) |
| `KebabMenu` | Menu contextuel ⋮ (Rename, Configure, Settings, Revoke/Delete) |
| `CopyableId` | Champ ID copiable avec feedback visuel |
| `ParticleCanvas` | Canvas d'arrière-plan animé sur la page de connexion |
| `BootLogs` | Terminal de logs de démarrage simulé sur la page de connexion |

#### Actions Spécialisées & Outillage Système
| Action / Composant | Endpoint / Trigger | Fonction |
|--------------------|-------------------|----------|
| **Kill Heavy Process** | `POST /api/nodes/{id}/heavy-processes/kill` | Termine un processus énergivore sur le Worker |
| **Renice Process** | `POST /api/nodes/{id}/heavy-processes/renice` | Ajuste la priorité CPU (nice) d'un processus |
| **Run Diagnostics** | `POST /api/nodes/{id}/diagnostics/run` | Déclenche un diagnostic système complet |
| **Audit Chain Verify** | `GET /api/admin/audit-verify` | Vérification cryptographique de la chaîne SHA256 des logs |
| **Worker OTA Update** | `POST /api/nodes/{id}/update` | Mise à jour à distance du binaire Go du Worker |
| **Regenerate Token** | `POST /api/nodes/{id}/regenerate-token` | Régénère le token d'enrôlement d'un nœud |
| **Acknowledge Alert** | `POST /api/admin/alerts/{id}/acknowledge` | Marque une alerte système comme résolue |
| **Demo Reset** | `POST /api/demo/reset` | Réinitialise l'état de démo et les proposals |

#### Copilot
| Composant | Fonction |
|-----------|----------|
| `CopilotHeader` | En-tête du panneau (titre, boutons) |
| `CopilotInput` | Champ de saisie message |
| `CopilotMessage` | Bulle de message (user/assistant) |
| `ProposalInline` | Proposal intégré dans le chat |

#### Disk Analysis
| Composant | Fonction |
|-----------|----------|
| `DiskTreemap` | Treemap SVG d3-hierarchy squarified |
| `DiskMountCards` | Cartes des points de montage |

### 1.4 API Endpoints identifiés (backend)

| Domaine | Endpoints clés |
|---------|---------------|
| **Auth** | `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/refresh`, `PUT /api/auth/change-password`, `POST /api/auth/force-change-password` |
| **Nodes** | `GET /api/nodes`, `GET /api/nodes/{id}`, `PUT /api/nodes/{id}`, `DELETE /api/nodes/{id}`, `POST /api/nodes/enroll`, `GET /api/nodes/{id}/disk-scan`, `POST /api/nodes/{id}/send-intent` |
| **Services** | `GET /api/nodes/{id}/services`, `POST /api/nodes/{id}/services/{name}/restart` |
| **Chat** | `POST /api/chat/send`, `GET /api/chat/conversations`, `GET /api/chat/{id}`, `DELETE /api/chat/{id}` |
| **Proposals** | `GET /api/proposals`, `POST /api/proposals/{id}/approve`, `POST /api/proposals/{id}/reject`, `POST /api/proposals/{id}/execute` |
| **Admin** | `GET /api/admin/users`, `POST /api/admin/users`, `PUT /api/admin/users/{id}`, `DELETE /api/admin/users/{id}`, `GET /api/admin/audit-log`, `GET /api/admin/config`, `PUT /api/admin/config`, `POST /api/admin/exec` |
| **Automations** | `GET /api/automations`, `POST /api/automations`, `PUT /api/automations/{id}`, `DELETE /api/automations/{id}`, `POST /api/automations/{id}/test` |
| **Plugins** | `GET /api/plugins`, `POST /api/plugins/{id}/toggle`, `POST /api/plugins/install`, `POST /api/plugins/upload` |
| **Metrics** | `GET /api/nodes/{id}/metrics` |
| **Profile Facts** | `GET /api/profile-facts`, `POST /api/profile-facts/{id}/approve`, `POST /api/profile-facts/{id}/reject` |
| **Investigations** | `GET /api/investigations` |
| **Demo** | `POST /api/demo/populate` |
| **Worker Binary** | `GET /api/worker/download` |
| **Node Events** | `GET /api/nodes/{id}/events` (SSE) |

### 1.5 Zones NON COUVRABLES (avec justification)

| Zone | Raison |
|------|--------|
| Zone | Couverture / Stratégie de vérification |
|------|---------------------------------------|
| **Vérification terrain sur serveurs réels** | **INCLUSE via SSH** : Accès aux hôtes **Oracle** (`flavio@youcloud.ovh`) et **Net Hunter Server** (`flavio@81.49.190.197`) pour vérifier directement l'état réel OS/Docker (`docker ps`, `systemctl status`, pids, uptime, etc.) avant et après chaque action déclenchée depuis l'UI. |
| **Exécution d'intents Worker (Services/Containers/Disk)** | **INCLUSE** : Testé de bout en bout (Front → API Master → WebSocket Worker → Système hôte distant → Vérification SSH terrain). |
| **Enrôlement réel d'un Worker** | **INCLUSE** : Testable si nécessaire via génération de token UI et exécution du kickstart via SSH sur un hôte de test. |
| **TLS/certificats** | Test infrastructure réseau, hors périmètre QA applicatif |
| **Performances sous charge** | Requiert outils de charge (k6, locust), hors périmètre QA fonctionnel |
| **Tests multi-navigateurs** | Limité à Chrome selon le brief |

---

### 1.6 Protocole de validation "Sur le terrain" (Ground Truth Verification via SSH)

Pour chaque action impactant l'infrastructure (redémarrage de service systemd, redémarrage/arrêt de conteneur Docker, modification de configuration, scan disque, etc.), la procédure de test suivra **obligatoirement 3 niveaux de vérification** :

```
[Étape 1 : Frontend UI] ──> [Étape 2 : API & Audit Master] ──> [Étape 3 : Vérification SSH "Sur le terrain"]
 (Action bouton/modal)       (Log Audit, Status 200, SSE)       (Commande CLI directe sur l'hôte distant)
```

#### Serveurs distants de test configurés :
1. **Oracle Server** : `flavio@youcloud.ovh` (IP / Tailscale `100.106.223.37`)
2. **Net Hunter Server** : `flavio@81.49.190.197`

#### Commandes de vérification terrain par type d'action :

- **Action Docker (ex: Restart / Stop Container)** :
  - *Front* : Clic sur "Restart" conteneur X.
  - *API* : Log audit enregistré, toast de succès.
  - *Vérification SSH* : `docker inspect --format='{{.State.StartedAt}} {{.State.Status}}' <container_id_or_name>` sur l'hôte correspondant pour vérifier l'horodatage exact du démarrage et le statut réel `running`.

- **Action Systemd (ex: Restart Service)** :
  - *Front* : Clic sur "Restart" service Y.
  - *API* : Log audit enregistré.
  - *Vérification SSH* : `systemctl status <service_name>` ou `journalctl -u <service_name> -n 20` pour valider le nouveau Main PID et le temps d'exécution (`Active: active (running) since ...`).

- **Scan Disque (DISK_SCAN)** :
  - *Front* : Visualisation Treemap.
  - *Vérification SSH* : Execution `du -sb <path>` ou `stat` sur le serveur distant pour valider que les tailles allouées et répertoires correspondent à 100% au rendu Treemap SVG.

- **Process Heavy / Renice / Kill** :
  - *Vérification SSH* : `ps aux | grep <process>` ou `top -b -n 1` pour vérifier la modification réelle de la priorité (nice) ou la terminaison du processus.

---

## 2. Matrice de tests exhaustive

### 2.1 Module AUTH — Connexion / Session / Déconnexion

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| A01 | Login nominal admin | Déconnecté | 1. Accéder à `/login` 2. Saisir `admin`/`admin` 3. Cliquer Login | Redirection vers `/`, sidebar visible avec rôle ADMIN | Critique | Nominal |
| A02 | Login mauvais mot de passe | Déconnecté | 1. Saisir `admin`/`wrongpass` 2. Cliquer Login | Message d'erreur explicite, pas de redirection | Critique | Erreur |
| A03 | Login utilisateur inexistant | Déconnecté | 1. Saisir `QA_ghost`/`pass` | Message d'erreur, pas d'info sur l'existence du user | Élevé | Sécurité |
| A04 | Login champs vides | Déconnecté | 1. Cliquer Login sans remplir | Validation front : champs requis | Moyen | Erreur |
| A05 | Login — champ password très long | Déconnecté | 1. Coller 5000 caractères dans password | Pas de crash, erreur gracieuse | Faible | Edge |
| A06 | Persistance session après refresh | Connecté admin | 1. Recharger la page (F5) | Session maintenue, pas de retour au login | Critique | Nominal |
| A07 | Persistance session nouvel onglet | Connecté admin | 1. Ouvrir `/` dans un nouvel onglet | Session active dans le nouvel onglet | Élevé | Nominal |
| A08 | Protection route — accès `/` déconnecté | Déconnecté | 1. Naviguer directement vers `/` | Redirection vers `/login` | Critique | Sécurité |
| A09 | Protection route — accès `/settings` déconnecté | Déconnecté | 1. Naviguer vers `/settings` | Redirection vers `/login` | Critique | Sécurité |
| A10 | Déconnexion | Connecté admin | 1. Trouver et cliquer le bouton de déconnexion | Retour au `/login`, token supprimé du localStorage | Critique | Nominal |
| A11 | Accès après déconnexion | Vient de se déconnecter | 1. Cliquer Retour navigateur | Pas d'accès aux données, redirection `/login` | Critique | Sécurité |
| A12 | Redirect post-login | Déconnecté, essaie `/settings` | 1. Accéder à `/settings` 2. Être redirigé `/login` 3. Se connecter | Redirection vers `/settings` (from state) | Élevé | UX |
| A13 | Affichage mot de passe (eye toggle) | Page login | 1. Vérifier s'il y a un toggle visibilité password | Password visible/masqué | Faible | UX |
| A14 | Login au clavier (Enter) | Page login, champs remplis | 1. Appuyer sur Enter | Soumission du formulaire | Moyen | Accessibilité |

### 2.2 Module DASHBOARD (`/`)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| D01 | Chargement dashboard | Connecté admin | 1. Naviguer vers `/` | HeroBanner, FleetGrid, sections chargées, pas de spinner infini | Critique | Nominal |
| D02 | Loading state (skeleton) | Connecté admin | 1. Observer au chargement initial | `DashboardSkeleton` visible puis remplacé par le contenu | Moyen | UX |
| D03 | Hero Banner contenu | Dashboard chargé | 1. Vérifier le HeroBanner | Insight IA ou message de bienvenue visible, pas de texte vide | Élevé | Nominal |
| D04 | Fleet Grid — cartes serveurs | Dashboard avec ≥1 nœud | 1. Vérifier la grille de nœuds | Cartes serveurs avec nom, statut (online/offline), métriques | Élevé | Nominal |
| D05 | Fleet Grid — état vide | Dashboard sans nœud connecté | 1. Vérifier la grille | Message empty state ou invitation à ajouter un serveur | Moyen | Vide |
| D06 | Clic NodeCard → NodeDetail | Dashboard avec nœud | 1. Cliquer une carte serveur | Navigation vers `/nodes/:id` | Élevé | Navigation |
| D07 | Proposals Section | Dashboard avec proposals pending | 1. Vérifier section proposals | ProposalCards visibles avec statut | Élevé | Nominal |
| D08 | Activity Section | Dashboard | 1. Vérifier section activité | Éléments d'activité récente listés | Moyen | Nominal |
| D09 | Containers Section | Dashboard avec Docker | 1. Vérifier section conteneurs | ContainerCards avec statuts | Moyen | Nominal |
| D10 | Insights Section | Dashboard | 1. Vérifier section insights | InsightCards visibles | Moyen | Nominal |
| D11 | PeriodSelector | Dashboard | 1. Changer la période (24h/7d/30d) | Données et graphiques mis à jour | Élevé | Interactif |
| D12 | TrendChart rendu | Dashboard avec données | 1. Vérifier les graphiques de tendance | Graphiques rendus correctement, pas de NaN/undefined | Élevé | Visuel |
| D13 | Responsive 1440px | Dashboard | 1. Vérifier layout à 1440px | Grille multi-colonnes, pas de débordement | Élevé | Responsive |
| D14 | Responsive 768px | Dashboard | 1. Redimensionner à 768px | Adaptation layout, pas de troncature | Élevé | Responsive |
| D15 | Responsive 375px | Dashboard | 1. Redimensionner à 375px | Layout mobile, pas de scroll horizontal | Élevé | Responsive |

### 2.3 Module SERVERS (`/servers`)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| S01 | Liste des serveurs | Connecté admin | 1. Naviguer `/servers` | Liste/grille de tous les nœuds avec statut | Critique | Nominal |
| S02 | Add Server — ouverture modale | Connecté admin | 1. Cliquer "Add Server" | `AddNodeModal` s'ouvre | Critique | Nominal |
| S03 | Add Server — génération token | Modale ouverte | 1. Remplir le formulaire 2. Valider | Token d'enrôlement généré, `JoinTokenDisplay` affiché | Critique | Nominal |
| S04 | Add Server — copie token | Token affiché | 1. Cliquer le bouton copier | Token copié dans le clipboard, feedback visuel | Élevé | UX |
| S05 | Add Server — fermeture modale | Modale ouverte | 1. Cliquer ✕ ou Échap ou clic extérieur | Modale fermée proprement | Moyen | UX |
| S06 | Kebab Menu — ouverture | Serveur dans la liste | 1. Cliquer ⋮ sur un serveur | Menu contextuel avec options | Élevé | Nominal |
| S07 | Rename Node — modale | Menu kebab ouvert | 1. Cliquer Rename | `RenameNodeModal` s'ouvre | Élevé | Nominal |
| S08 | Rename Node — validation | Modale rename ouverte | 1. Saisir `QA_renamed_server` 2. Valider | Nom mis à jour dans la liste, toast succès | Élevé | CRUD |
| S09 | Rename Node — nom vide | Modale rename | 1. Effacer le nom 2. Valider | Validation front bloque la soumission | Moyen | Erreur |
| S10 | Rename Node — annulation | Modale rename | 1. Cliquer Annuler | Modale fermée, aucune modification | Moyen | Annulation |
| S11 | Delete Node — modale confirmation | Menu kebab | 1. Cliquer Delete | `ConfirmDeleteModal` s'ouvre avec avertissement | Critique | CRUD |
| S12 | Delete Node — annulation | Modale delete ouverte | 1. Cliquer Annuler | Nœud non supprimé | Critique | Annulation |
| S13 | Delete Node — confirmation | Modale confirmée | 1. Confirmer suppression | Nœud supprimé de la liste, toast succès | Critique | CRUD ⚠️ |
| S14 | Server Config — modale | Menu kebab | 1. Cliquer Configure | `ServerConfigModal` s'ouvre | Élevé | Nominal |
| S15 | Clic serveur → NodeDetail | Liste serveurs | 1. Cliquer sur un serveur | Navigation vers `/nodes/:id` | Élevé | Navigation |
| S16 | État vide — aucun serveur | Aucun nœud | 1. Vérifier `/servers` | EmptyState avec CTA "Add Server" | Moyen | Vide |
| S17 | Responsive 1440/768/375 | Page serveurs | Vérifier les 3 largeurs | Layout adapté, pas de débordement | Élevé | Responsive |

### 2.4 Module NODE DETAIL (`/nodes/:id`)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| N01 | Chargement page | Nœud existant | 1. Naviguer `/nodes/:id` | Header avec nom et statut, onglets visibles | Critique | Nominal |
| N02 | Header — infos nœud | Page chargée | 1. Vérifier le `NodeDetailHeader` | Nom, statut online/offline, OS, IP | Élevé | Nominal |
| N03 | Navigation onglets | Page chargée | 1. Cliquer chaque onglet successivement | Contenu change, URL `?tab=` mise à jour | Élevé | Navigation |
| N04 | URL directe avec tab | — | 1. Accéder `/nodes/:id?tab=metrics` | Onglet metrics actif directement | Élevé | Deep link |
| N05 | Onglet Insights | Onglet insights actif | 1. Vérifier le contenu | InsightsTab avec cartes d'insights IA | Élevé | Nominal |
| N06 | Onglet Metrics — cartes | Onglet metrics | 1. Vérifier `MetricsOverviewCards` | Cartes CPU, RAM, Disk, Load avec valeurs | Élevé | Nominal |
| N07 | Onglet Metrics — graphiques | Onglet metrics | 1. Vérifier les graphiques temporels | Graphiques rendus, axes lisibles, tooltips | Élevé | Visuel |
| N08 | Onglet Metrics — tooltip | Onglet metrics | 1. Survoler un point du graphique | `MetricsTooltip` avec valeur et timestamp | Moyen | Interactif |
| N09 | Onglet Services — liste | Onglet services | 1. Vérifier la liste | Services systemd avec nom, statut (active/failed/inactive) | Élevé | Nominal |
| N10 | Onglet Services — état vide | Nœud sans services | 1. Vérifier | EmptyState ou message "no services" | Moyen | Vide |
| N11 | Onglet Containers — liste | Onglet containers | 1. Vérifier | Conteneurs Docker avec nom, image, statut | Élevé | Nominal |
| N12 | Onglet Containers — état vide | Nœud sans Docker | 1. Vérifier | Message approprié | Moyen | Vide |
| N13 | Onglet Logs — viewer | Onglet logs | 1. Vérifier le viewer | Logs affichés avec horodatage, scroll | Élevé | Nominal |
| N14 | Onglet Logs — état vide | Pas de logs | 1. Vérifier | Message "no logs" | Moyen | Vide |
| N15 | Onglet Disk — treemap | Onglet disk, scan existant | 1. Vérifier le `DiskTreemap` | Treemap SVG rendu avec couleurs amber→red | Élevé | Visuel |
| N16 | Onglet Disk — mount cards | Onglet disk | 1. Vérifier `DiskMountCards` | Cartes de points de montage avec usage | Élevé | Nominal |
| N17 | Onglet Disk — drill-down | Treemap visible | 1. Cliquer sur un répertoire | Zoom dans le sous-arbre, breadcrumb mis à jour | Élevé | Interactif |
| N18 | Onglet Disk — rescan (admin) | Onglet disk | 1. Cliquer bouton rescan | Déclenchement d'un nouveau scan (ou feedback si Worker absent) | Élevé | Action |
| N19 | Onglet Settings — config nœud | Onglet settings | 1. Vérifier `NodeSettingsTab` | Configuration du nœud avec enrollment key visible | Élevé | Nominal |
| N20 | Nœud inexistant — URL invalide | — | 1. Accéder `/nodes/nonexistent-uuid` | Erreur 404 ou redirection gracieuse | Élevé | Erreur |
| N21 | Responsive onglets | Page NodeDetail | 1. Vérifier aux 3 largeurs | Onglets scrollables ou dropdown, pas de coupure | Élevé | Responsive |

### 2.5 Module COPILOT (Panneau latéral)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| C01 | Ouverture panneau | Connecté admin | 1. Cliquer "Copilot" dans sidebar | Panneau latéral `CopilotPanel` s'ouvre en drawer | Critique | Nominal |
| C02 | Fermeture panneau | Panneau ouvert | 1. Cliquer ✕ ou Échap | Panneau se ferme | Élevé | UX |
| C03 | Envoi message | Panneau ouvert | 1. Taper un message 2. Appuyer Enter/Send | Message utilisateur affiché, réponse IA en streaming | Critique | Nominal |
| C04 | Envoi message vide | Panneau ouvert | 1. Cliquer Send sans texte | Bouton désactivé ou pas d'envoi | Moyen | Erreur |
| C05 | Streaming réponse | Message envoyé | 1. Observer la réponse | Texte arrive progressivement (streaming), pas de blocage | Élevé | UX |
| C06 | Proposal inline | Réponse avec proposal | 1. Observer `ProposalInline` | Action proposée affichée dans le chat | Élevé | Nominal |
| C07 | Historique conversations | Panneau | 1. Ouvrir historique (AllChatsModal) | Liste des conversations passées | Élevé | Nominal |
| C08 | Sélection conversation | AllChatsModal ouvert | 1. Cliquer une conversation | Messages de cette conversation chargés | Élevé | Navigation |
| C09 | Nouvelle conversation | Panneau | 1. Cliquer "New Chat" | Conversation vierge | Élevé | Nominal |
| C10 | Responsive panneau | Panneau ouvert | 1. Vérifier aux 3 largeurs | Panneau pleine largeur en mobile, 50% en tablette, drawer en desktop | Élevé | Responsive |

### 2.6 Module PROPOSALS (`/proposals`)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| P01 | Liste proposals | Connecté admin | 1. Naviguer `/proposals` | Liste des proposals avec statut, nœud, action | Critique | Nominal |
| P02 | Filtre par statut | Page proposals | 1. Sélectionner filtre (ALL/PENDING/APPROVED/...) | Liste filtrée, URL `?status=` mise à jour | Élevé | Filtre |
| P03 | Clic proposal → modale | Proposal dans la liste | 1. Cliquer une ligne | `ProposalModal` s'ouvre avec détails | Élevé | Nominal |
| P04 | Approve proposal | Modale ouverte, status PENDING | 1. Cliquer Approve | Statut passe à APPROVED, toast succès | Critique | CRUD |
| P05 | Reject proposal | Modale ouverte, status PENDING | 1. Cliquer Reject 2. Saisir raison dans `ProposalRejectModal` 3. Confirmer | Statut passe à REJECTED | Critique | CRUD |
| P06 | Reject — raison vide | ProposalRejectModal | 1. Laisser raison vide 2. Confirmer | Validation bloque ou accepte (vérifier le comportement) | Moyen | Erreur |
| P07 | Operational Memory — Profile Facts | Section Profile Facts | 1. Vérifier les facts LLM-proposed | Facts listées avec statut pending/approved/rejected | Élevé | Nominal |
| P08 | Approve/Reject fact | Fact pending | 1. Approuver ou rejeter | Statut mis à jour | Élevé | CRUD |
| P09 | Badge sidebar proposals | Dashboard | 1. Vérifier le badge dans sidebar | Nombre de proposals PENDING affiché | Moyen | UX |
| P10 | État vide proposals | Aucune proposal | 1. Vérifier page | EmptyState approprié | Moyen | Vide |
| P11 | Responsive | Page proposals | 1. Vérifier aux 3 largeurs | Tableau/cartes adaptés | Élevé | Responsive |

### 2.7 Module AUTOMATIONS (`/automations`)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| AU01 | Liste rules | Connecté admin | 1. Naviguer `/automations` | Liste des automation rules sous forme de `RuleCard` | Élevé | Nominal |
| AU02 | Create rule — ouverture modale | Page automations | 1. Cliquer "Create Rule" | `RuleFormModal` s'ouvre | Élevé | Nominal |
| AU03 | Create rule — formulaire nominal | Modale ouverte | 1. Remplir nom `QA_test_rule`, conditions, actions 2. Valider | Rule créée, apparaît dans la liste, toast succès | Élevé | CRUD |
| AU04 | Create rule — champs vides | Modale ouverte | 1. Soumettre sans remplir | Validation front bloque | Moyen | Erreur |
| AU05 | Edit rule | Rule existante | 1. Cliquer Edit sur `RuleCard` 2. Modifier 3. Sauvegarder | Modification sauvegardée | Élevé | CRUD |
| AU06 | Delete rule | Rule existante | 1. Cliquer Delete 2. Confirmer | Rule supprimée | Élevé | CRUD ⚠️ |
| AU07 | Test rule | Rule existante | 1. Cliquer Test 2. Observer `TestRuleModal` | Résultat du test affiché | Élevé | Nominal |
| AU08 | Toggle enable/disable | Rule existante | 1. Basculer l'état enabled | Statut mis à jour visuellement | Élevé | Interactif |
| AU09 | Log drawer | Rule avec historique | 1. Ouvrir `AutomationLogDrawer` | Logs d'exécution listés | Moyen | Nominal |
| AU10 | État vide | Aucune rule | 1. Vérifier page | EmptyState | Moyen | Vide |
| AU11 | Responsive | Page automations | 1. Vérifier aux 3 largeurs | Layout adapté | Élevé | Responsive |

### 2.8 Module PLUGINS — Inventaire, Lifecycle & Pages dynamiques (`/plugins`)

#### 2.8.1 Inventaire des plugins backend

| Plugin ID | Nom | Type | Protégé | Hooks | Config Schema | Page Frontend | Sidebar |
|-----------|-----|------|---------|-------|---------------|---------------|---------|
| `metrics` | Metrics Collector | Built-in ✅ | ✅ Oui | `get_supported_actions`, `normalize_status_report`, `on_status_report` | `polling_interval` (int, 60), `retention_days` (int, 30) | `MetricsHistory` | ✅ Oui (via PluginRouter) |
| `docker` | Docker Container Orchestrator | Built-in ✅ | ✅ Oui | `get_supported_actions` | `docker_host` (string), `auto_restart_failed` (bool) | `DockerContainers` | ❌ Non |
| `systemd` | Systemd Service Manager | Built-in ✅ | ✅ Oui | `get_supported_actions` | — | `SystemdServices` | ❌ Non |
| `plex` | Plex Media Server Integration | Installable | ❌ Non | `on_status_report`, `get_heavy_process_patterns` | `plex_token` (string), `plex_port_override` (int), `cpu_threshold` (int, 80) | `PlexAdmin` (onglets: Sessions, Libraries, Users) | ✅ Oui |
| `disk_analysis` | Analyse Disque | Frontend-only | ❌ Non | — | — | (via NodeDetail DiskTab) | ❌ Non |
| `clean_logs` | Log File Housekeeping | Installable | ❌ Non | `on_status_report`, `get_supported_actions` | — | — | ❌ Non |

#### 2.8.2 Tests — Page Plugins (Onglet Installed)

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL01 | Chargement onglet Installed | Connecté admin | 1. Naviguer `/plugins` | PluginCards affichées pour chaque plugin. Compteur "X installés / Y chargés" visible | `GET /api/admin/plugins` retourne `plugins[]` + `loaded_plugins[]` | Critique | Nominal |
| PL02 | Loading skeleton | Navigation vers `/plugins` | 1. Observer le chargement | Skeleton cards pulsantes (3 cartes) puis contenu réel | — | Moyen | UX |
| PL03 | PluginCard — infos affichées | Onglet Installed | 1. Vérifier chaque carte | Nom, description, statut (loaded/unloaded), module path, hooks badges | — | Élevé | Visuel |
| PL04 | PluginCard — erreur affichée | Plugin avec erreur | 1. Vérifier la carte | Bandeau d'erreur rouge avec message | — | Élevé | Erreur |
| PL05 | Bouton Refresh | Onglet Installed | 1. Cliquer Refresh (🔄) | Liste re-chargée, icône spin pendant le chargement | `GET /api/admin/plugins` appelé à nouveau | Moyen | Interactif |

#### 2.8.3 Tests — Toggle (Activer/Désactiver) chaque plugin

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL10 | Toggle OFF — metrics | Plugin metrics loaded | 1. Cliquer l'icône toggle (ToggleRight → ToggleLeft) | Statut passe à "unloaded", toast "Désactivé", Spinner pendant l'opération | `POST /api/admin/plugins/metrics/toggle` → `{loaded: false}` | ⚠️ Élevé | Interactif |
| PL11 | Toggle ON — metrics | Plugin metrics unloaded | 1. Cliquer l'icône toggle | Statut repasse à "loaded", toast "Activé" | `POST /api/admin/plugins/metrics/toggle` → `{loaded: true}` | ⚠️ Élevé | Interactif |
| PL12 | Toggle OFF — docker | Plugin docker loaded | 1. Toggle OFF | "unloaded", toast succès | `POST /api/admin/plugins/docker/toggle` → `{loaded: false}` | ⚠️ Élevé | Interactif |
| PL13 | Toggle ON — docker | Plugin docker unloaded | 1. Toggle ON | "loaded", toast succès | `POST /api/admin/plugins/docker/toggle` → `{loaded: true}` | ⚠️ Élevé | Interactif |
| PL14 | Toggle OFF — systemd | Plugin systemd loaded | 1. Toggle OFF | "unloaded" | `POST /api/admin/plugins/systemd/toggle` | ⚠️ Élevé | Interactif |
| PL15 | Toggle ON — systemd | Plugin systemd unloaded | 1. Toggle ON | "loaded" | `POST /api/admin/plugins/systemd/toggle` | ⚠️ Élevé | Interactif |
| PL16 | Toggle OFF — plex | Plugin plex loaded | 1. Toggle OFF | "unloaded", sidebar Plex link disappears | `POST /api/admin/plugins/plex/toggle` + `GET /api/plugins/pages` re-fetched | ⚠️ Élevé | Interactif |
| PL17 | Toggle ON — plex | Plugin plex unloaded | 1. Toggle ON | "loaded", sidebar Plex link appears | Idem | ⚠️ Élevé | Interactif |
| PL18 | Toggle sidebar update | Plugin avec sidebar:true toggled | 1. Toggle Plex ou Metrics 2. Vérifier sidebar | Lien dynamique ajouté/supprimé de la sidebar en temps réel | `GET /api/plugins/pages` re-fetched par `pluginStore.fetchPluginPages()` | Élevé | Navigation |

#### 2.8.4 Tests — Plugin Detail Modal & Configuration

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL20 | Ouvrir detail modale — metrics | Onglet Installed | 1. Cliquer la carte Metrics Collector | `PluginDetailModal` s'ouvre : nom, version, statut loaded, description, hooks listés, `PluginConfigForm` présent | — | Élevé | Nominal |
| PL21 | Config form — metrics (polling_interval) | Modale metrics ouverte | 1. Modifier `Polling Interval` à 120 2. Cliquer Enregistrer | Toast "Configuration enregistrée", valeur persistée | `POST /api/admin/plugins/metrics/config` body `{polling_interval: 120, retention_days: 30}` | Élevé | CRUD |
| PL22 | Config form — metrics (retention_days) | Modale metrics | 1. Modifier `Retention Days` à 7 2. Enregistrer | Toast succès | `POST /api/admin/plugins/metrics/config` body `{..., retention_days: 7}` | Élevé | CRUD |
| PL23 | Config form — docker (docker_host) | Modale docker | 1. Vérifier champ `Docker Host Socket` (défaut `unix:///var/run/docker.sock`) 2. Modifier 3. Enregistrer | Toast succès | `POST /api/admin/plugins/docker/config` | Élevé | CRUD |
| PL24 | Config form — docker (auto_restart_failed toggle) | Modale docker | 1. Basculer le toggle `Auto Restart Failed` | Toggle change visuellement (Activé/Désactivé) | Persisté au save | Élevé | Interactif |
| PL25 | Config form — plex (plex_token) | Modale plex | 1. Saisir un token test 2. Enregistrer | Toast succès | `POST /api/admin/plugins/plex/config` body `{plex_token: "QA_test_token", ...}` | Élevé | CRUD |
| PL26 | Config form — plex (cpu_threshold) | Modale plex | 1. Modifier CPU threshold à 90 2. Enregistrer | Valeur sauvegardée | Backend vérifie int parsing | Moyen | CRUD |
| PL27 | Config form — annuler | Modale ouverte | 1. Modifier des valeurs 2. Cliquer Annuler | Modale fermée, valeurs non sauvegardées | Pas d'appel API | Moyen | Annulation |
| PL28 | Config form — erreur save | Modale ouverte | 1. Simuler erreur (si possible) | Toast erreur "Erreur de configuration" | Backend retourne erreur | Moyen | Erreur |
| PL29 | Fermeture modale — ✕ | Modale ouverte | 1. Cliquer ✕ | Modale fermée | — | Faible | UX |
| PL30 | Fermeture modale — backdrop | Modale ouverte | 1. Cliquer en dehors de la modale | Modale fermée | — | Faible | UX |
| PL31 | Deep link `?open=plex` | — | 1. Accéder `/plugins?open=plex` | Plugin Plex auto-sélectionné, modale ouverte | — | Moyen | Deep link |

#### 2.8.5 Tests — Onglet Registry & Installation

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL40 | Chargement onglet Registry | Onglet Registry cliqué | 1. Cliquer l'onglet "Registry" | Loading skeleton puis `RegistryPluginCards` affichées | `GET /api/admin/plugins/registry` retourne `{plugins: [...]}` | Élevé | Nominal |
| PL41 | Registry — affichage cartes | Registry chargé | 1. Vérifier chaque carte | Nom, description, auteur, version, bouton Install | — | Élevé | Visuel |
| PL42 | Registry — plugin déjà installé | Plugin déjà installé (ex: plex) | 1. Vérifier sa carte dans Registry | Bouton grisé "Installé" (disabled), carte opacity réduite | Comparaison `plugins.some(p => p.id === plugin.id)` | Élevé | Nominal |
| PL43 | Install plugin depuis registry | Plugin non installé | 1. Cliquer "Installer" | Spinner "Installation...", puis toast succès, plugin apparaît dans Installed | `POST /api/admin/plugins/registry/{id}/install` → `{status: "success"}`, puis `GET /api/admin/plugins` | Critique | CRUD |
| PL44 | Install — erreur réseau/registry | Registry indisponible | 1. Cliquer Install (si erreur) | Toast erreur avec message | Backend renvoie erreur (download fail ou compile fail) | Élevé | Erreur |
| PL45 | Registry — état vide | Aucun plugin dans le registry | 1. Vérifier l'onglet | EmptyState avec message | — | Moyen | Vide |

#### 2.8.6 Tests — Upload de plugin (.py)

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL50 | Upload — bouton visible admin | Connecté admin, `/plugins` | 1. Vérifier bouton "Upload" | Bouton visible avec icône Upload | — | Élevé | Nominal |
| PL51 | Upload — sélection fichier .py | Bouton Upload | 1. Cliquer Upload 2. Sélectionner un fichier `.py` valide | Spinner uploading, toast "Plugin uploaded", liste rafraîchie | `POST /api/admin/plugins/upload` (FormData), puis `GET /api/admin/plugins` | Élevé | Upload |
| PL52 | Upload — fichier non-.py | Bouton Upload | 1. Sélectionner un fichier `.txt` | Filtre natif du `<input accept=".py">` devrait empêcher. Si contourné → erreur backend | Backend rejette si pas `.py` | Moyen | Erreur |
| PL53 | Upload — fichier .py invalide (syntax error) | Bouton Upload | 1. Uploader un `.py` avec erreur de syntaxe | Toast erreur "Upload failed" — `compile()` échoue côté backend | Backend: `compile(source, filename, "exec")` échoue | Élevé | Erreur |
| PL54 | Upload — fichier .py sans `register(pm)` | Bouton Upload | 1. Uploader un `.py` valide mais sans `register(pm)` | Erreur backend — vérification AST échoue | Backend: AST check rejette | Élevé | Erreur |
| PL55 | Upload — spinner pendant upload | Upload en cours | 1. Observer | Bouton Upload devient Spinner | — | Faible | UX |
| PL56 | Upload — reset input après upload | Après upload (succès ou échec) | 1. Vérifier que le file input est réinitialisé | `fileInputRef.current.value = ''` — possible de re-uploader | — | Faible | UX |

#### 2.8.7 Tests — Désinstallation de plugin

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL60 | Delete — plugin non-protégé (ex: clean_logs) | Plugin clean_logs installé | 1. Cliquer 🗑 sur la carte 2. Confirmer (`window.confirm`) | Toast "Plugin deleted", carte disparaît | `DELETE /api/admin/plugins/clean_logs` → `{status: "deleted"}`, fichier `.py` supprimé du disque | Critique ⚠️ | CRUD |
| PL61 | Delete — plugin protégé (metrics) | Plugin metrics | 1. Cliquer 🗑  2. Confirmer | Erreur backend — "Cannot uninstall built-in plugin" | `DELETE /api/admin/plugins/metrics` → HTTP 403/400 | Élevé | Erreur |
| PL62 | Delete — plugin protégé (docker) | Plugin docker | 1. Tenter suppression | Erreur — protégé | Backend rejette | Élevé | Erreur |
| PL63 | Delete — plugin protégé (systemd) | Plugin systemd | 1. Tenter suppression | Erreur — protégé | Backend rejette | Élevé | Erreur |
| PL64 | Delete — annulation confirm dialog | Plugin non-protégé | 1. Cliquer 🗑 2. Cliquer Annuler dans confirm() | Plugin non supprimé | Pas d'appel API | Moyen | Annulation |
| PL65 | Delete — spinner pendant suppression | Suppression en cours | 1. Observer | Icône 🗑 remplacée par Spinner | — | Faible | UX |

#### 2.8.8 Tests — Pages Frontend dynamiques des plugins

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL70 | Plex — page PlexAdmin | Plugin plex loaded, sidebar Plex visible | 1. Cliquer "Plex" dans sidebar | Page `PlexAdmin` chargée (via `PluginRouter` → lazy import) | `GET /api/plugins/pages` inclut l'entrée plex | Élevé | Navigation |
| PL71 | Plex — sélection nœud | Page PlexAdmin | 1. Sélectionner un nœud dans le dropdown | Plex detection lancée pour ce nœud | `GET /api/plugins/plex/{node_id}/detect` | Élevé | Interactif |
| PL72 | Plex — détection succès | Nœud avec Plex installé | 1. Observer détection | Badge "Détecté" ou "Non détecté", port affiché | Backend retourne `{detected: true/false, port: 32400}` | Élevé | Nominal |
| PL73 | Plex — onglet Sessions | Page PlexAdmin, nœud sélectionné | 1. Vérifier onglet Sessions | Sessions actives listées (titre, utilisateur, durée) | `GET /api/plugins/plex/{node_id}/sessions` | Élevé | Nominal |
| PL74 | Plex — onglet Libraries | Page PlexAdmin | 1. Cliquer onglet Libraries | Bibliothèques Plex listées | `GET /api/plugins/plex/{node_id}/library` | Élevé | Nominal |
| PL75 | Plex — onglet Users | Page PlexAdmin | 1. Cliquer onglet Users | Utilisateurs Plex listés | `GET /api/plugins/plex/{node_id}/users` | Élevé | Nominal |
| PL76 | Plex — page quand plugin désactivé | Plugin plex unloaded | 1. Accéder `/plugins?open=plex` | Pas de lien sidebar, route non accessible | `GET /api/plugins/pages` ne retourne pas l'entrée plex | Élevé | Sécurité |
| PL77 | Plex — Refresh données | Page PlexAdmin | 1. Cliquer bouton Refresh | Données re-chargées | API re-appelées | Moyen | Interactif |
| PL80 | Metrics History — page | Plugin metrics loaded | 1. Accéder via PluginRouter | Page `MetricsHistory` chargée avec graphiques Recharts (AreaChart) | `GET /api/plugins/metrics/history?period=24h` | Élevé | Nominal |
| PL81 | Metrics History — sélecteur nœud | Page MetricsHistory | 1. Sélectionner un nœud (ou "all") | Graphique mis à jour avec données du nœud | API `?node_id=...` | Élevé | Filtre |
| PL82 | Metrics History — sélecteur période | Page MetricsHistory | 1. Changer période (24h / 7d / 30d) | Graphique mis à jour | API `?period=7d` | Élevé | Filtre |
| PL83 | Metrics History — graphiques rendus | Données présentes | 1. Vérifier les graphiques | CPU, RAM, Disk area charts rendus correctement, axes lisibles | — | Élevé | Visuel |
| PL84 | Metrics History — état vide | Aucune donnée | 1. Vérifier | Message "pas de données" ou graphique vide | API retourne `{history: []}` | Moyen | Vide |
| PL85 | Metrics History — erreur chargement | Erreur API | 1. Observer | Toast erreur | API renvoie erreur | Moyen | Erreur |
| PL90 | Docker Containers — page plugin | Plugin docker loaded | 1. Accéder via PluginRouter | Page `DockerContainers` chargée avec liste conteneurs cross-nodes | `GET /api/plugins/docker/containers` | Élevé | Nominal |
| PL91 | Docker — filtre par nœud | Page DockerContainers | 1. Sélectionner un nœud | Liste filtrée | API `?node_id=...` | Élevé | Filtre |
| PL92 | Docker — filtre par état | Page DockerContainers | 1. Sélectionner état (running/stopped/all) | Liste filtrée | Filtrage client-side | Élevé | Filtre |
| PL93 | Docker — recherche | Page DockerContainers | 1. Taper dans la barre de recherche | Conteneurs filtrés par nom ou image | Filtrage client-side | Élevé | Filtre |
| PL94 | Docker — action Restart | Conteneur dans la liste | 1. Cliquer bouton Restart | Spinner pendant l'action, toast succès, liste re-chargée après 2s | `POST /api/plugins/docker/containers/{id}/restart` body `{node_id: ...}` | Critique ⚠️ | Action |
| PL95 | Docker — état vide | Aucun conteneur | 1. Vérifier | EmptyState approprié | — | Moyen | Vide |
| PL100 | Systemd Services — page plugin | Plugin systemd loaded | 1. Accéder via PluginRouter | Page `SystemdServices` chargée avec liste services cross-nodes | `GET /api/plugins/systemd/services` | Élevé | Nominal |
| PL101 | Systemd — filtre par nœud | Page SystemdServices | 1. Sélectionner nœud | Liste filtrée | API `?node_id=...` | Élevé | Filtre |
| PL102 | Systemd — filtre par état | Page SystemdServices | 1. Filtrer (active/failed/all) | Services filtrés | Client-side | Élevé | Filtre |
| PL103 | Systemd — recherche | Page SystemdServices | 1. Chercher par nom service | Services filtrés | Client-side | Élevé | Filtre |
| PL104 | Systemd — action Restart | Service dans la liste | 1. Cliquer Restart | Spinner, toast succès, refresh après 2s | `POST /api/plugins/systemd/services/{name}/restart` body `{node_id: ...}` | Critique ⚠️ | Action |
| PL105 | Systemd — état vide | Aucun service | 1. Vérifier | EmptyState | — | Moyen | Vide |

#### 2.8.9 Tests — PluginRouter & Composant non compilé

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| PL110 | PluginRouter — loading state | Navigation vers page plugin | 1. Observer | Spinner de chargement `Suspense` | `GET /api/plugins/pages` | Faible | UX |
| PL111 | PluginRouter — composant non compilé | Plugin avec composant inconnu | 1. Si un plugin déclare un composant non dans PLUGIN_COMPONENTS | Fallback "Composant non compilé" avec code du composant | — | Moyen | Erreur |
| PL112 | PluginRouter — RBAC filtre | Viewer connecté (si testable) | 1. Accéder à page plugin admin | Pages filtrées par rôle | `allowedPages` filtrage côté client | Élevé | Sécurité |

#### 2.8.10 Tests — Responsive plugins

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| PL120 | Plugin page — 1440px | `/plugins` | 1. Vérifier à 1440px | Grille 3 colonnes `lg:grid-cols-3` | Élevé | Responsive |
| PL121 | Plugin page — 768px | `/plugins` | 1. Vérifier à 768px | Grille 2 colonnes `sm:grid-cols-2` | Élevé | Responsive |
| PL122 | Plugin page — 375px | `/plugins` | 1. Vérifier à 375px | Grille 1 colonne `grid-cols-1`, pas de débordement | Élevé | Responsive |
| PL123 | PluginDetailModal — mobile | Modale ouverte, 375px | 1. Vérifier modale | Modale pleine largeur, scroll vertical si nécessaire, formulaire lisible | Élevé | Responsive |
| PL124 | Pages plugin (Plex/Metrics/Docker/Systemd) — responsive | Pages plugin | 1. Vérifier aux 3 largeurs | Layout adapté sans débordement | Élevé | Responsive |

### 2.9 Module SETTINGS (`/settings`)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| ST01 | Onglet Profile | Connecté admin | 1. Naviguer `/settings` | `ProfileSettingsTab` avec préférences utilisateur | Élevé | Nominal |
| ST02 | Changement mot de passe | Onglet profile | 1. Remplir ancien + nouveau mdp 2. Valider | Mot de passe changé, toast succès | Critique | CRUD |
| ST03 | Changement mdp — ancien incorrect | Onglet profile | 1. Saisir mauvais ancien mdp | Erreur explicite | Élevé | Erreur |
| ST04 | Changement mdp — confirmation ≠ | Onglet profile | 1. Nouveau mdp ≠ confirmation | Erreur de validation | Moyen | Erreur |
| ST05 | Changement langue | Onglet profile | 1. Changer la langue | Interface traduite | Moyen | Interactif |
| ST06 | Changement thème/apparence | Onglet profile | 1. Changer thème clair/sombre | Thème appliqué immédiatement | Moyen | Interactif |
| ST07 | Onglet System — General | Admin, onglet system | 1. Cliquer General | `GeneralSettingsTab` avec config master | Élevé | Nominal |
| ST08 | Onglet System — LLM | Admin | 1. Cliquer LLM | `LLMSettingsTab` avec clé API, modèle, endpoint | Critique | Nominal |
| ST09 | LLM — sauvegarde config | LLMSettingsTab | 1. Modifier la config LLM 2. Sauvegarder | Configuration sauvegardée, toast succès | Critique | CRUD |
| ST10 | LLM — clé API masquée | LLMSettingsTab | 1. Vérifier affichage clé | Clé API masquée (•••) ou partiellement visible | Élevé | Sécurité |
| ST11 | Onglet System — Security | Admin | 1. Cliquer Security | `SecuritySettingsTab` avec paramètres sécurité | Élevé | Nominal |
| ST12 | Onglet System — Plugins | Admin | 1. Cliquer Plugins | `PluginsSettingsTab` | Moyen | Nominal |
| ST13 | Responsive | Page settings | 1. Vérifier aux 3 largeurs | Onglets et formulaires adaptés | Élevé | Responsive |

### 2.10 Module COMMAND PALETTE (Cmd+K)

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| CP01 | Ouverture | Connecté admin | 1. Appuyer Cmd+K (ou Ctrl+K) | `CommandPalette` s'ouvre en overlay | Élevé | Nominal |
| CP02 | Recherche | Palette ouverte | 1. Taper un terme de recherche | Résultats filtrés en temps réel | Élevé | Interactif |
| CP03 | Navigation via résultat | Résultats affichés | 1. Cliquer un résultat | Navigation vers la page correspondante | Élevé | Navigation |
| CP04 | Fermeture Échap | Palette ouverte | 1. Appuyer Échap | Palette fermée | Moyen | UX |
| CP05 | Fermeture clic extérieur | Palette ouverte | 1. Cliquer en dehors | Palette fermée | Moyen | UX |
| CP06 | Résultats vides | Palette | 1. Taper terme sans résultat | Message "no results" | Moyen | Vide |

### 2.11 Module LAYOUT & NAVIGATION GLOBALE

| # | Test | Préconditions | Étapes | Résultat attendu | Risque | Type |
|---|------|---------------|--------|-------------------|--------|------|
| L01 | Sidebar — tous les liens | Connecté admin | 1. Cliquer chaque item de la sidebar | Navigation correcte vers chaque page | Critique | Navigation |
| L02 | Sidebar — section admin collapsible | Sidebar | 1. Ouvrir/fermer section Admin | Accordion fonctionne | Moyen | Interactif |
| L03 | Sidebar — badge proposals | Proposals pending | 1. Vérifier badge | Nombre affiché, mis à jour en temps réel | Moyen | UX |
| L04 | Sidebar — Server Selector | Sidebar | 1. Vérifier le banner de sélection serveur | Hostname et indicateur connectivité visibles | Élevé | Nominal |
| L05 | TopBar | Toute page | 1. Vérifier la barre supérieure | Éléments attendus présents (titre page, actions) | Élevé | Nominal |
| L06 | Footer profil → Settings | Sidebar footer | 1. Cliquer le profil | Navigation vers `/settings` | Moyen | Navigation |
| L07 | URL catch-all → redirect | — | 1. Accéder `/this-does-not-exist` | Redirection vers `/` | Moyen | Fallback |
| L08 | Bouton retour navigateur | Depuis NodeDetail | 1. Cliquer ← navigateur | Retour à la page précédente | Élevé | Navigation |
| L09 | Toast notification | Après une action (save, delete) | 1. Observer les toasts | Toast visible avec message approprié, disparaît après timeout | Élevé | UX |
| L10 | Toast empilage | Plusieurs actions rapides | 1. Déclencher plusieurs toasts | Toasts empilés sans chevauchement, tous lisibles | Moyen | UX |
| L11 | Sidebar responsive 375px | Mobile | 1. Vérifier sidebar | Sidebar masquée ou burger menu | Critique | Responsive |
| L12 | Logo link → Dashboard | Toute page | 1. Cliquer logo VIGILE | Navigation vers `/` | Faible | Navigation |

### 2.12 Module AUDIT CHAIN VERIFICATION & ALERTS (`/api/admin/audit-verify` & `/api/admin/alerts`)

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| AU_V01 | Audit verify — chaîne intacte | Admin | 1. Déclencher vérification d'intégrité de la chaîne | HTTP 200 OK `{valid: true}`, rapport d'intégrité validé | `GET /api/admin/audit-verify` retourne `valid: true` | Critique | Sécurité |
| AL_01 | Alerts list | Operator/Admin | 1. Consulter les alertes système | Liste d'alertes filtrable par sévérité (`critical`, `warning`, `info`) et statut | `GET /api/admin/alerts` | Élevé | Nominal |
| AL_02 | Alerts summary | Operator/Admin | 1. Vérifier le résumé des alertes dans le header (`NotifBell`) | Nombre d'alertes actives groupées par sévérité | `GET /api/admin/alerts/summary` | Élevé | Nominal |
| AL_03 | Acknowledge alert | Alerte active | 1. Cliquer "Acknowledge" / "Résoudre" sur une alerte | Alerte marquée comme `resolved`, toast succès | `POST /api/admin/alerts/{id}/acknowledge` | Élevé | Action |

### 2.13 Module HEAVY PROCESSES & DIAGNOSTICS (`/api/nodes/{id}/...`)

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| HP_01 | Run node diagnostics | Onglet insights ou Copilot | 1. Cliquer "Lancer les diagnostics" | Diagnostic exécuté, rapport affiché avec préconisations | `POST /api/nodes/{id}/diagnostics/run` | Élevé | Action |
| HP_02 | Renice heavy process | Nœud avec charge CPU élevée | 1. Sélectionner un processus gourmand 2. Modifier la priorité nice | Processus ré-assigné avec nouvelle priorité | `POST /api/nodes/{id}/heavy-processes/renice` | Élevé | Action ⚠️ |
| HP_03 | Kill heavy process | Processus problématique | 1. Déclencher terminaison du processus | Intent envoyé au Worker, confirmation de terminaison | `POST /api/nodes/{id}/heavy-processes/kill` | Critique | Action ⚠️ |

### 2.14 Module DEMO SYSTEM & WORKER BINARY OTA (`/api/demo` & `/api/nodes/binary`)

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| DM_01 | Connexion utilisateur Demo (`guest`/`guest`) | Déconnecté | 1. Cliquer "Tester en mode Demo" sur la page de login | Connexion directe rôle admin (démo), notification mode démo | `POST /api/auth/login` credentials guest | Moyen | Nominal |
| DM_02 | Mutations bloquées en mode Demo | Utilisateur Demo | 1. Tenter de modifier config LLM ou upload plugin | Action rejetée avec message 403 "Modifications non autorisées en mode démo" | HTTP 403 Forbidden | Élevé | Sécurité |
| DM_03 | Demo reset | Utilisateur Demo | 1. Déclencher reset démo | Proposals démo réinitialisées, état restauré | `POST /api/demo/reset` | Moyen | Action |
| WB_01 | Téléchargement binaire Worker Go | Modale Add Server | 1. Demander téléchargement du binaire selon OS/Arch (linux/amd64) | Binaire téléchargé ou servi avec checksum SHA256 | `GET /api/nodes/binary/{os}/{arch}/worker` | Élevé | Nominal |
| WB_02 | Worker OTA Update | Onglet Node Settings | 1. Cliquer "Update Worker Binary" | Intent d'update OTA envoyé au Worker | `POST /api/nodes/{id}/update` | Élevé | Action |
| WB_03 | Regenerate Join Token | Onglet Node Settings | 1. Cliquer "Regenerate Token" | Nouveau token d'enrôlement généré pour le nœud | `POST /api/nodes/{id}/regenerate-token` | Élevé | Action |

### 2.15 Module SSE EVENTS & RATE LIMITING COOLDOWN

| # | Test | Préconditions | Étapes | Résultat attendu | Vérif Backend | Risque | Type |
|---|------|---------------|--------|-------------------|---------------|--------|------|
| SSE_01 | SSE stream connexion | Connecté avec token JWT | 1. Charger la page et observer la connexion EventSource | SSE connecté à `/api/nodes/events/stream?token=...`, réception des événements `node.state` | Flux SSE `text/event-stream` actif | Élevé | Nominal |
| SSE_02 | SSE notification nouveau nœud | Événement `UNCONFIGURED` | 1. Simuler l'arrivée d'un nœud | Toast notification en temps réel informant du raccordement du nœud | Événement SSE déclenche `addToast` | Élevé | UX |
| RL_01 | Rate limit login | Déconnecté | 1. Tenter >5 requêtes login en 1 minute | HTTP 429 Too Many Requests | Rate limit dependency `LOGIN_LIMIT` | Élevé | Sécurité |
| RL_02 | Toast cooldown anti-flood | 429 généré | 1. Observer l'affichage des toasts 429 | Seul un toast d'avertissement est affiché toutes les 6 secondes (cooldown 6000ms) | Protection `RATE_LIMIT_TOAST_COOLDOWN_MS` | Moyen | UX |

---

## 3. Scénarios transverses obligatoires

### 3.1 Cohérence visuelle (à vérifier sur CHAQUE page aux 3 largeurs)

| # | Vérification | Détail |
|---|-------------|--------|
| V01 | Éléments coupés | Aucun texte, bouton ou carte tronqué |
| V02 | Chevauchements | Aucun élément ne se superpose à un autre |
| V03 | Contraste | Texte lisible sur tous les fonds (ratio WCAG AA ≥ 4.5:1) |
| V04 | Boutons inactifs | Boutons disabled visuellement distincts |
| V05 | Textes tronqués | Textes longs avec ellipsis (…) ou wrap propre |
| V06 | Scroll involontaire | Pas de scroll horizontal involontaire |
| V07 | Modales non fermables | Toutes les modales ont un moyen de fermeture (✕, Échap, backdrop) |
| V08 | Icônes | Toutes les icônes chargées (pas de □ ou ?) |
| V09 | Polices | Polices chargées (pas de fallback serif visible) |
| V10 | Animations | Transitions fluides, pas de saccade |

### 3.2 Erreurs techniques (à vérifier en continu)

| # | Vérification | Méthode |
|---|-------------|---------|
| T01 | Erreurs console JS | DevTools Console ouverte en permanence |
| T02 | Erreurs réseau (4xx, 5xx) | DevTools Network filtré par erreurs |
| T03 | Réponses API anormales | Vérifier les payloads JSON pour champs null/undefined inattendus |
| T04 | Liens cassés | Vérifier navigation, aucun 404 |
| T05 | Warnings React | Pas de key warnings, deprecated API, etc. |
| T06 | Memory leaks | Observer les onglets ouverts longtemps |

### 3.3 Accessibilité pratique

| # | Vérification | Méthode |
|---|-------------|---------|
| AC01 | Navigation clavier | Tab through tous les éléments interactifs |
| AC02 | Focus visible | Outline visible sur l'élément focusé |
| AC03 | Labels formulaires | Tous les inputs ont un label associé |
| AC04 | Fermeture modale Échap | Toutes les modales se ferment avec Échap |
| AC05 | ARIA attributes | Vérifier les attributs ARIA sur les composants interactifs |
| AC06 | Skip links | Vérifier si un lien "Skip to content" existe |

### 3.4 Session & Sécurité

| # | Test | Détail |
|---|------|--------|
| SE01 | Token expiration | Laisser la session idle, vérifier le refresh token |
| SE02 | Manipulation localStorage | Supprimer `vigile_access_token` → vérifier redirection |
| SE03 | Token corrompu | Modifier le token dans localStorage → vérifier erreur gracieuse |
| SE04 | Double onglet | Ouvrir 2 onglets, déconnecter dans un → vérifier l'autre |
| SE05 | CORS | Vérifier qu'aucune erreur CORS n'apparaît |

---

## 4. Stratégie de données

### 4.1 Actions SANS risque (lecture seule)

| Action | Détail |
|--------|--------|
| Navigation entre pages | Aucune modification |
| Consultation Dashboard | Lecture seule |
| Consultation NodeDetail (tous onglets) | Lecture seule |
| Consultation Proposals | Lecture seule |
| Consultation Plugins | Lecture seule |
| Consultation Settings (lecture) | Lecture seule |
| Ouverture/fermeture modales | Pas de side-effect |
| Command Palette recherche | Lecture seule |
| Consultation Audit Log | Lecture seule |
| Copilot — lecture historique | Lecture seule |

### 4.2 Opérations DESTRUCTRICES ou IRRÉVERSIBLES ⚠️

| Action | Risque | Mitigation |
|--------|--------|------------|
| **Delete Node** (`DELETE /api/nodes/{id}`) | ❌ Nœud supprimé définitivement | NE PAS supprimer de nœuds réels. Créer un `QA_test_node` d'abord si possible |
| **Delete Automation Rule** (`DELETE /api/automations/{id}`) | ❌ Rule supprimée | Créer une rule `QA_test_rule` pour le test, supprimer uniquement celle-ci |
| **Delete Chat Conversation** (`DELETE /api/chat/{id}`) | ⚠️ Conversation supprimée | Utiliser une conversation `QA_` |
| **Change Admin Password** (`PUT /api/auth/change-password`) | ⚠️ Password réel changé | ⚠️ **NE PAS modifier** le password admin sans accord explicite |
| **Approve/Execute Proposal** | ⚠️ Action exécutée sur un Worker réel | ⚠️ **NE PAS approuver** de proposals sur des nœuds de production sans accord |
| **Modify LLM Config** | ⚠️ Config prod modifiée | ⚠️ **NE PAS modifier** la clé API LLM sans accord. Vérifier affichage seulement |
| **Toggle Plugin** | ⚠️ Plugin activé/désactivé en production | Tester toggle seulement sur des plugins non critiques, ou demander accord |
| **Demo Populate** (`POST /api/demo/populate`) | ⚠️ Données de démo ajoutées | Demander accord avant exécution |
| **Admin Exec** (`POST /api/admin/exec`) | ❌ **Exécution dynamique Python** | NE JAMAIS utiliser |

### 4.3 Données de test préfixées `QA_`

| Donnée | Préfixe | Usage |
|--------|---------|-------|
| Nom de nœud (rename) | `QA_renamed_server` | Test rename, restaurer le nom original après |
| Automation rule | `QA_test_rule` | CRUD complet, supprimer après test |
| Message Copilot | `QA_test_message` | Test conversation, supprimer conversation après |
| Conversation Copilot | `QA_test_conversation` | Créée puis supprimée |

### 4.4 Plan de nettoyage post-test

1. Supprimer toute automation rule nommée `QA_*`
2. Supprimer toute conversation Copilot créée pendant les tests
3. Restaurer le nom original de tout nœud renommé en `QA_*`
4. Ne PAS restaurer les proposals approuvées/rejetées (elles sont idempotentes dans le log)
5. Vérifier qu'aucune donnée `QA_*` ne persiste

---

## 5. Format du rapport final

### 5.1 Structure du rapport

```markdown
# Rapport QA End-to-End — Vigile
**Date** : YYYY-MM-DD
**Testeur** : Agent QA
**URL** : vigile.youcloud.ovh
**Navigateur** : Chrome (version)
**Identifiants** : admin/admin

## Résumé exécutif
- Pages testées : X/Y
- Tests exécutés : X
- ✅ Réussis : X
- ❌ Échoués : X
- ⏸ Bloqués : X
- 🔇 NON TESTÉS : X (avec raisons)

## Matrice de couverture
| Page | Desktop 1440 | Tablette 768 | Mobile 375 | Statut |
|------|:---:|:---:|:---:|--------|

## Anomalies trouvées
### ANO-001 : [Titre court]
- **Sévérité** : Critique / Élevée / Moyenne / Faible
- **Page** : URL
- **Largeur** : Desktop / Tablette / Mobile
- **Étapes de reproduction** :
  1. ...
- **Résultat attendu** : ...
- **Résultat obtenu** : ...
- **Screenshot** : [image embarquée]
- **Erreurs Console/Network** : ...
- **Correction proposée** : ...
- **Retest après correction** : ⏳ / ✅ / ❌

## Tests détaillés par module
### Module AUTH
| # | Test | Desktop | Tablette | Mobile | Résultat | Notes |
|---|------|:---:|:---:|:---:|--------|-------|

## Fonctionnalités NON TESTÉES
| Fonctionnalité | Raison |
|---------------|--------|
```

---

## A. Plan de test — Résumé

| Phase | Contenu | Durée estimée |
|-------|---------|---------------|
| **Phase 1 — Auth & Session** | Tests A01→A14, SE01→SE05 | ~20 min |
| **Phase 2 — Dashboard** | Tests D01→D15 | ~15 min |
| **Phase 3 — Servers** | Tests S01→S17 | ~20 min |
| **Phase 4 — Node Detail** | Tests N01→N21 | ~30 min |
| **Phase 5 — Copilot** | Tests C01→C10 | ~15 min |
| **Phase 6 — Proposals** | Tests P01→P11 | ~15 min |
| **Phase 7 — Automations** | Tests AU01→AU11 | ~15 min |
| **Phase 8 — Plugins** | Tests PL01→PL08 | ~10 min |
| **Phase 9 — Settings** | Tests ST01→ST13 | ~15 min |
| **Phase 10 — Command Palette** | Tests CP01→CP06 | ~5 min |
| **Phase 11 — Layout & Nav** | Tests L01→L12 | ~10 min |
| **Phase 12 — Transverse** | Tests V01→V10, T01→T06, AC01→AC06 | ~20 min |
| **Phase 13 — Nettoyage** | Suppression données QA_ | ~5 min |

---

## B. Validations de l'utilisateur (Confirmées)

> [!NOTE]
> 1. **Nœuds connectés** : ✅ **Validé par l'utilisateur**. Des Workers réels (Oracle et Net Hunter Server) sont actifs et connectés. Les tests de bout en bout avec vérification SSH terrain seront exécutés.

> [!NOTE]
> 2. **Données existantes** : Données réelles conservées. Pas de purge globale. Seules des données temporaires `QA_*` seront créées et nettoyées à la fin.

> [!NOTE]
> 3. **Changement de mot de passe** : ✅ **Autorisé par l'utilisateur**. Le changement de mot de passe admin sera testé puis réinitialisé à `admin` immédiatement après le test.

> [!NOTE]
> 4. **Proposals & Actions d'infrastructure** : ✅ **Autorisés sans restriction par l'utilisateur**. L'approbation, le rejet et l'exécution de toutes les proposals et actions (restart conteneurs, services systemd, renice/kill, scans) seront testés réellement sur tous les serveurs, avec contrôle SSH systématique.

> [!NOTE]
> 5. **Config LLM** : Test de validation et sauvegarde de configuration LLM autorisé.

> [!NOTE]
> 6. **Vérifications SSH Terrain** : ✅ **Autorisées par l'utilisateur** sur Oracle (`flavio@youcloud.ovh`) et Net Hunter Server (`flavio@81.49.190.197`).

---

## C. Estimation du nombre de scénarios

| Catégorie | Nombre de cas |
|-----------|:---:|
| Auth & Session | 19 |
| Dashboard | 15 |
| Servers | 17 |
| Node Detail | 21 |
| Copilot | 10 |
| Proposals | 11 |
| Automations | 11 |
| **Plugins — Page Installed** | **5** |
| **Plugins — Toggle (par plugin)** | **9** |
| **Plugins — Config & Detail Modal** | **12** |
| **Plugins — Registry & Install** | **6** |
| **Plugins — Upload** | **7** |
| **Plugins — Désinstallation** | **6** |
| **Plugins — Pages dynamiques (Plex/Metrics/Docker/Systemd)** | **26** |
| **Plugins — PluginRouter & Responsive** | **8** |
| Settings | 13 |
| Command Palette | 6 |
| Layout & Navigation | 12 |
| **Audit Chain & Alerts** | **4** |
| **Heavy Processes & Diagnostics** | **3** |
| **Demo System & Worker Binary OTA** | **6** |
| **SSE Events & Rate Limiting** | **4** |
| Cohérence visuelle | 10 |
| Erreurs techniques | 6 |
| Accessibilité | 6 |
| Session & Sécurité | 5 |
| **TOTAL** | **~280 scénarios** |

> Chaque scénario sera exécuté jusqu'à 3 fois (desktop, tablette, mobile) selon pertinence, ce qui donne un total d'environ **700+ vérifications** unitaires.

---

## D. Liste des actions potentiellement destructrices

| # | Action | Endpoint | Conséquence | Mitigation |
|---|--------|----------|-------------|------------|
| 1 | **Supprimer un nœud** | `DELETE /api/nodes/{id}` | Nœud retiré de la BDD, historique perdu | Créer un nœud QA_ temporaire si possible |
| 2 | **Supprimer une automation rule** | `DELETE /api/automations/{id}` | Rule supprimée | Tester uniquement sur `QA_test_rule` |
| 3 | **Supprimer une conversation Copilot** | `DELETE /api/chat/{id}` | Historique perdu | Tester sur conversation QA_ |
| 4 | **Changer le mot de passe admin** | `PUT /api/auth/change-password` | MDP production modifié | Remettre `admin` immédiatement après |
| 5 | **Approuver une proposal** | `POST /api/proposals/{id}/approve` | Déclenche action sur Worker | Validé par l'utilisateur avec contrôle SSH |
| 6 | **Exécuter une proposal** | `POST /api/proposals/{id}/execute` | Exécution sur Worker réel | Validé par l'utilisateur avec contrôle SSH |
| 7 | **Modifier config LLM** | `PUT /api/admin/config` | Config prod changée | Validé par l'utilisateur |
| 8 | **Toggle plugin** | `POST /api/plugins/{id}/toggle` | Plugin activé/désactivé | Tester par paire (remettre dans l'état initial) |
| 9 | **Demo populate & Reset** | `POST /api/demo/populate` / `reset` | Données démo modifiées | Utilisé uniquement en mode démo |
| 10 | **Admin exec** | `POST /api/admin/exec` | Exécution Python arbitraire | ❌ **INTERDIT** |
| 11 | **Rename nœud** | `PUT /api/nodes/{id}` | Nom modifié | Restaurer le nom original après |
| 12 | **Désinstaller plugin** | `DELETE /api/admin/plugins/{id}` | Code supprimé du disque | Tester UNIQUEMENT sur `clean_logs` (non-protégé), puis réinstaller depuis registry |
| 13 | **Kill Heavy Process** | `POST /api/nodes/{id}/heavy-processes/kill` | Processus système arrêté sur Worker | Validé par l'utilisateur avec contrôle SSH |
| 14 | **Renice Heavy Process** | `POST /api/nodes/{id}/heavy-processes/renice` | Priorité CPU modifiée sur Worker | Validé par l'utilisateur avec contrôle SSH |
| 15 | **Worker OTA Update** | `POST /api/nodes/{id}/update` | Mise à jour du binaire Worker | Contrôle SSH |

---

## TODOs

- [x] 1. Phase 1 — Auth & Session (A01→A14, SE01→SE05)
- [x] 2. Phase 2 — Dashboard (D01→D15)
- [x] 3. Phase 3 — Servers (S01→S17)
- [x] 4. Phase 4 — Node Detail (N01→N21)
- [x] 5. Phase 5 — Copilot (C01→C10)
- [x] 6. Phase 6 — Proposals (P01→P11)
- [x] 7. Phase 7 — Automations (AU01→AU11)
- [x] 8. Phase 8 — Plugins (PL01→PL08)
- [x] 9. Phase 9 — Settings (ST01→ST13)
- [x] 10. Phase 10 — Command Palette (CP01→CP06)
- [x] 11. Phase 11 — Layout & Nav (L01→L12)
- [x] 12. Phase 12 — Transverse (V01→V10, T01→T06, AC01→AC06)
- [x] 13. Phase 13 — Nettoyage (QA_ data cleanup)

## Final Verification Wave

- [x] F1. Full report review
- [x] F2. Screenshot evidence check
- [x] F3. Anomaly triage
- [x] F4. Recommendations prioritized

---
