# Audit Vigile — 2026-06-15
Sprint en cours : 5

## Résumé exécutif
| Priorité | Nombre |
|---|---|
| 🔴 Critique | 15 |
| 🟠 Important | 25 |
| 🟡 Signal | 22 |
| 📊 Métrique | 3 |
| 🔍 Manuel requis | 3 |

**Top 3 urgences :**
1. **[B-03] Exceptions silencieuses (`pass` sans log)** dans les modules critiques de sécurité (`security_manager.py`, `auth.py`, `deps.py`) et la base de données (`database.py`), masquant des vulnérabilités ou dysfonctionnements sévères.
2. **[B-12] CORS wildcard dynamique avec credentials** dans `main.py` qui renvoie systématiquement l'Origin reçu pour contourner la restriction de sécurité sur les requêtes authentifiées, désactivant la protection du navigateur.
3. **[B-05 / B-06] Requêtes N+1 et SQL dynamique (F-string)** dans `node_manager.py` posant un risque d'injection SQL et de blocage concurrent lors des transactions.

---

## 🔴 Critique (bloquants)

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Fichier :** [master/core/security_manager.py:304](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py#L304)
- **Extrait :**
  ```python
  except JWTError:
      pass
  ```
- **Problème :** L'exception de signature ou d'expiration JWT is capturée et ignorée silencieusement lors de la validation du jeton d'accès.
- **Action requise :** Enregistrer l'erreur de décodage du token dans les journaux système avec un niveau `warning`.

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Fichier :** [master/core/security_manager.py:393](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py#L393)
- **Extrait :**
  ```python
  except JWTError:
      pass
  ```
- **Problème :** L'erreur de décodage ou de structure JWT pour les tokens de rafraîchissement est ignorée silencieusement.
- **Action requise :** Logger l'exception ou lever une alerte de sécurité.

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Fichier :** [master/core/security_manager.py:412](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/security_manager.py#L412)
- **Extrait :**
  ```python
  except JWTError:
      pass
  ```
- **Problème :** Interception silencieuse d'une erreur de jeton lors de la validation asynchrone.
- **Action requise :** Logger la cause précise de l'échec de la signature.

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Fichier :** [master/db/database.py:56](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L56)
- **Extrait :**
  ```python
  except Exception:
      pass
  ```
- **Problème :** L'échec de fermeture ou de libération d'une connexion de base de données est passé sous silence.
- **Action requise :** Ajouter un log d'avertissement pour signaler la perte ou le problème réseau avec la DB.

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Fichier :** [master/api/auth.py:170](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L170)
- **Extrait :**
  ```python
  except Exception:
      pass
  ```
- **Problème :** L'interception globale de toute erreur lors d'un échec d'authentification masque les erreurs systèmes.
- **Action requise :** Logger l'exception pour permettre le diagnostic de pannes serveur.

### [B-03] Exception interceptée silencieusement (pass sans log)
- **Fichier :** [master/api/deps.py:209](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py#L209)
- **Extrait :**
  ```python
  except RuntimeError:
      pass
  ```
- **Problème :** L'échec d'initialisation du client LLM ou de sa configuration est silencieux.
- **Action requise :** Logger un message de warning signalant que le copilote n'est pas instancié.

### [B-05] Appel 'await db.' dans une boucle (Risque N+1 ou lock DB)
- **Fichier :** [master/core/node_manager.py:251](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L251)
- **Extrait :** `await db.execute(query, params)`
- **Problème :** Des écritures successives individuelles en base de données sont exécutées dans une boucle `for`.
- **Action requise :** Regrouper les requêtes en une opération d'écriture groupée (`executemany`).

### [B-05] Appel 'await db.' dans une boucle (Risque N+1 ou lock DB)
- **Fichier :** [master/core/node_manager.py:252](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L252)
- **Extrait :** `await db.commit()`
- **Problème :** Un commit individuel est effectué à chaque itération dans la boucle de mise à jour, provoquant des locks réguliers.
- **Action requise :** Exécuter un unique commit après la boucle de traitement.

### [B-06] F-string utilisé pour construire une requête SQL (Risque d'injection)
- **Fichier :** [master/core/node_manager.py:250](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L250)
- **Extrait :** `query = f"UPDATE nodes SET {', '.join(fields)} WHERE id = ?"`
- **Problème :** L'utilisation de f-string dynamique pour construire le corps d'une requête SQL est un anti-pattern à risque d'injection SQL.
- **Action requise :** Valider explicitement la liste blanche des champs modifiables ou utiliser un constructeur de requêtes sécurisé.

### [B-06] F-string utilisé pour construire une requête SQL (Risque d'injection)
- **Fichier :** [master/core/node_manager.py:397](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L397)
- **Extrait :** `f"UPDATE nodes SET {set_clause} WHERE id = ?"`
- **Problème :** Concaténation de chaînes SQL avec f-string dans la mise à jour des états.
- **Action requise :** Remplacer par des requêtes préparées avec paramètres.

### [B-06] F-string utilisé pour construire une requête SQL (Risque d'injection)
- **Fichier :** [master/core/audit.py:209](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py#L209)
- **Extrait :** `sql = f"SELECT {_columns} FROM audit_log ORDER BY sequence DESC LIMIT ?"`
- **Problème :** Interpolation de colonnes via f-string dans les requêtes de l'audit.
- **Action requise :** Utiliser des requêtes statiques explicites ou un mapping sûr.

### [B-06] F-string utilisé pour construire une requête SQL (Risque d'injection)
- **Fichier :** [master/api/audit.py:77](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/audit.py#L77)
- **Extrait :** `count_sql = f"SELECT COUNT(*) as cnt FROM audit_log {where}"`
- **Problème :** La construction dynamique de la clause WHERE avec f-string crée une surface d'injection.
- **Action requise :** Paramétrer les clauses de recherche.

### [B-12] CORS wildcard + credentials avec contournement dynamique
- **Fichier :** [master/main.py:237](file:///Users/flavio/Documents/Projets/Youcloud-API/master/main.py#L237)
- **Extrait :**
  ```python
  @app.middleware("http")
  async def _cors_echo_origin(request: Request, call_next: Callable) -> Response:
  ```
- **Problème :** Le middleware renvoie dynamiquement l'en-tête de requête Origin comme origine autorisée afin de contourner l'interdiction par le navigateur d'utiliser un wildcard (*) avec des cookies d'authentification.
- **Action requise :** Supprimer le middleware et lister les origines autorisées explicitement dans la configuration.

### [B-04] Appel synchrone bloquant dans une fonction asynchrone
- **Fichier :** [master/api/admin.py:133](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L133)
- **Extrait :** `with override_path.open("w", encoding="utf-8") as f:`
- **Problème :** L'écriture synchrone de fichier sur disque bloque la boucle d'événements asynchrone (event loop) de FastAPI.
- **Action requise :** Utiliser `aiofiles` ou déléguer l'écriture synchrone à un thread-pool (`run_in_executor`).

### [B-04] Appel synchrone bloquant dans une fonction asynchrone
- **Fichier :** [master/api/admin.py:342](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L342)
- **Extrait :** `with open(plugin_path, "wb") as f:`
- **Problème :** Téléchargement synchrone et écriture sur disque bloquants dans un endpoint asynchrone.
- **Action requise :** Remplacer par une écriture non bloquante.

---

## 🟠 Important (sprint suivant)

### [B-01] os.getenv ou os.environ utilisé en dehors de config.py
- **Fichier :** [master/core/secret_loader.py:49](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/secret_loader.py#L49)
- **Extrait :** `value = os.environ.get(env_var)`
- **Problème :** L'accès direct aux variables d'environnement en dehors de config.py viole la centralisation de la configuration.
- **Action requise :** Charger ces variables dans `config.py` et les injecter.

### [B-01] os.getenv ou os.environ utilisé en dehors de config.py
- **Fichier :** [master/db/migrations.py:110](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L110)
- **Extrait :** `must_change = 1 if os.getenv("TESTING") == "true" else 0`
- **Problème :** os.getenv utilisé dans un script de migration.
- **Action requise :** Utiliser les options de configuration passées à Alembic ou injecter via les paramètres globaux.

### [B-02] settings importé directement dans core/ ou api/
- **Fichier :** [master/api/auth.py:21](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/auth.py#L21)
- **Extrait :** `from master.config import settings`
- **Problème :** L'import de `settings` direct dans les fichiers de l'API brise les principes d'injection de dépendances (DI).
- **Action requise :** Utiliser la dépendance FastAPI `Depends(get_settings)`.

### [B-02] settings importé directement dans core/ ou api/
- **Fichier :** [master/api/deps.py:53](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/deps.py#L53)
- **Extrait :** `from master.config import settings`
- **Problème :** Import direct enfreignant les règles d'injection.
- **Action requise :** Injecter settings via les constructeurs.

### [B-08] Paramètre ou valeur de retour non typé
- **Fichier :** [master/core/audit.py:67](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py#L67)
- **Extrait :** `def compute_entry_hash(`
- **Problème :** La signature de fonction ne possède pas de type de retour explicite.
- **Action requise :** Ajouter l'annotation `-> str`.

### [B-09] Mutation DB sans log_action
- **Fichier :** [master/api/admin.py:503](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/admin.py#L503)
- **Extrait :** `await db.execute("DELETE FROM plugin_configs WHERE plugin_id = ?", (plugin_id,))`
- **Problème :** Suppression en DB effectuée sans laisser de trace d'activité dans le registre d'audit.
- **Action requise :** Insérer un appel à `log_action` après la suppression pour historiser la mutation.

### [B-10] Import différé dans le corps d'une fonction
- **Fichier :** [master/core/node_manager.py:201](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L201)
- **Extrait :** `from master.plugins.docker_plugin import parse_container_list`
- **Problème :** Import local dans une fonction pour pallier une mauvaise séparation ou une dépendance circulaire.
- **Action requise :** Déplacer l'import en début de module et corriger l'architecture si nécessaire.

### [F-01] Style inline React détecté
- **Fichier :** [frontend/src/components/ui/CardSkeleton.tsx:12](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/ui/CardSkeleton.tsx#L12)
- **Extrait :** `style={{ width, height }}`
- **Problème :** L'usage de l'attribut `style` en ligne complique la maintenance et la personnalisation visuelle.
- **Action requise :** Utiliser des variables CSS globales ou des classes Tailwind CSS.

### [F-01] Couleur ou valeur arbitraire Tailwind codée en dur
- **Fichier :** [frontend/src/components/layout/TopBar.tsx:151](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/TopBar.tsx#L151)
- **Extrait :** `t === 'warm-dark' ? 'bg-[#6366f1]' : ...`
- **Problème :** Utilisation de codes hexadécimaux arbitraires brisant la consistance thématique de Tailwind.
- **Action requise :** Déclarer ces couleurs dans les variables de thème de Tailwind CSS v4.

### [F-01] Couleur ou valeur arbitraire Tailwind codée en dur
- **Fichier :** [frontend/src/components/layout/Sidebar.tsx:475](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/Sidebar.tsx#L475)
- **Extrait :** `: 'border-[#2dd4bf] shadow-[0_0_8px_rgba(45,212,191,0.15)] bg-teal-500/5'`
- **Problème :** Utilisation de valeurs d'ombres et de bordures arbitraires codées en dur.
- **Action requise :** Définir des tokens sémantiques ou réutiliser des classes prédéfinies.

### [F-02] Magic number utilisé dans un timer/setTimeout/setInterval
- **Fichier :** [frontend/src/components/layout/NotifBell.tsx:36](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/NotifBell.tsx#L36)
- **Extrait :** `const interval = setInterval(loadProposals, 20000);`
- **Problème :** Le délai de 20s (20000ms) est configuré en dur sans constante nommée.
- **Action requise :** Remplacer par une constante nommée ou une valeur de configuration globale.

### [F-07] Composant volumineux dépassant le seuil de 250 lignes (God component)
- **Fichier :** [frontend/src/pages/NodeDetail.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/pages/NodeDetail.tsx)
- **Extrait :** `Taille : 860 lignes`
- **Problème :** Le composant gère trop de responsabilités d'affichage et d'états, le rendant complexe à maintenir.
- **Action requise :** Découper la page en sous-composants spécialisés (onglets, cartes de métriques).

### [F-07] Composant volumineux dépassant le seuil de 250 lignes (God component)
- **Fichier :** [frontend/src/components/layout/Sidebar.tsx](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/Sidebar.tsx)
- **Extrait :** `Taille : 607 lignes`
- **Problème :** Le composant de navigation latérale est excessivement grand.
- **Action requise :** Extraire les éléments de liens de navigation et d'états dans des composants dédiés.

### [G-01] Erreur ignorée via underscore
- **Fichier :** [worker/services.go:48](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/services.go#L48)
- **Extrait :** `outJSON, _ := json.Marshal(services)`
- **Problème :** L'erreur potentielle générée par `json.Marshal` est silencieusement ignorée, ce qui pourrait masquer une corruption d'objets.
- **Action requise :** Gérer l'erreur retournée explicitement.

### [G-01] Erreur ignorée via underscore
- **Fichier :** [worker/connection.go:139](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L139)
- **Extrait :** `challenge, _ := challengeMsg["challenge"].(string)`
- **Problème :** L'échec potentiel de conversion de type (type assertion) est ignoré, ce qui peut causer des comportements imprévus si le format du message est invalide.
- **Action requise :** Valider la conversion avec `challenge, ok := ...`.

### [G-02] Goroutine démarrée sans signal de shutdown (risque de fuite)
- **Fichier :** [worker/connection.go:212](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L212)
- **Extrait :** `go func() { ... }()`
- **Problème :** La boucle infinie de la goroutine n'écoute pas de signal d'arrêt ou de contexte d'annulation, créant un risque de fuite de goroutine lors des déconnexions/reconnexions.
- **Action requise :** Passer un contexte d'annulation pour forcer la fermeture propre de la goroutine.

### [G-03] Goroutine démarrée sans recover() (Risque de crash global)
- **Fichier :** [worker/connection.go:212](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L212)
- **Extrait :** `go func() { ... }()`
- **Problème :** Si une panique non interceptée survient dans la goroutine, tout l'exécutable du worker s'arrêtera brutalement.
- **Action requise :** Encapsuler la routine dans un bloc `defer recover()` pour intercepter les paniques.

### [G-03] Goroutine démarrée sans recover() (Risque de crash global)
- **Fichier :** [worker/main.go:110](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/main.go#L110)
- **Extrait :** `go func() { sig := ... }()`
- **Problème :** Goroutine de gestion de signaux OS lancée sans intercepteur de panique.
- **Action requise :** Ajouter un recover pour la robustesse.

### [G-03] Assertion de type directe pouvant provoquer un panic
- **Fichier :** [worker/enrollment.go:35](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/enrollment.go#L35)
- **Extrait :** `pub := priv.Public().(ed25519.PublicKey)`
- **Problème :** L'assertion de type directe sans validation risque de faire crasher le worker si le format de clé privée retourné est corrompu ou modifié.
- **Action requise :** Utiliser la forme sécurisée `pub, ok := priv.Public().(ed25519.PublicKey)`.

### [G-04] Timeout / Deadline TCP hardcodé (Magic Number)
- **Fichier :** [worker/connection.go:214](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L214)
- **Extrait :** `_ = ws.SetReadDeadline(time.Now().Add(90 * time.Second))`
- **Problème :** Utilisation directe de `90 * time.Second` en dur dans le code d'affectation de deadline de socket.
- **Action requise :** Utiliser la constante définie `heartbeatTimeout` à la place.

### [G-06] Fonction sans passage de context.Context
- **Fichier :** [worker/containers.go:29](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/containers.go#L29)
- **Extrait :** `func dockerAPI(method, path string, body io.Reader)`
- **Problème :** Absence de propagation du contexte empêchant l'annulation propre des requêtes HTTP vers l'API Docker.
- **Action requise :** Ajouter un paramètre `ctx context.Context` à la signature de la fonction et l'utiliser dans la construction de la requête HTTP.

### [G-06] Fonction sans passage de context.Context
- **Fichier :** [worker/connection.go:48](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/connection.go#L48)
- **Extrait :** `func NewWorkerConn(...)`
- **Problème :** Initialisation de la structure réseau sans contexte de contrôle de cycle de vie.
- **Action requise :** Intégrer un `context.Context` pour coordonner le démarrage et l'arrêt réseau.

---

## 🟡 Signaux (à surveiller)

### [F-05] Type 'any' TypeScript non justifié
- **Fichier :** [frontend/src/components/ui/EmptyState.tsx:29](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/ui/EmptyState.tsx#L29)
- **Extrait :** `className: \`\${(icon.props as any).className || ''}...\``
- **Problème :** L'usage du type `any` supprime la sécurité du typage statique de TypeScript.
- **Action requise :** Typer explicitement l'objet (par exemple, en `React.HTMLAttributes<SVGElement>`).

### [F-05] Type 'any' TypeScript non justifié
- **Fichier :** [frontend/src/components/layout/TopBar.tsx:157](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/components/layout/TopBar.tsx#L157)
- **Extrait :** `onClick={() => setTheme(t as any)}`
- **Problème :** Cast abusif de type vers `any` pour contourner le typage du thème de l'application.
- **Action requise :** Configurer un type union valide pour les thèmes (`'light' | 'dark' | ...`).

### [F-06] Utilisation de console.error au lieu d'un gestionnaire d'erreur
- **Fichier :** [frontend/src/store/chatStore.ts:287](file:///Users/flavio/Documents/Projets/Youcloud-API/frontend/src/store/chatStore.ts#L287)
- **Extrait :** `console.error('SSE Error:', err);`
- **Problème :** Journalisation d'erreurs en production effectuée de manière brute dans la console du navigateur.
- **Action requise :** Utiliser un service d'observabilité ou un gestionnaire global d'erreurs.

### [G-05] Appel système ou exécution de commande système en dur
- **Fichier :** [worker/services.go:17](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/services.go#L17)
- **Extrait :** `cmd := exec.CommandContext(ctx, "systemctl", ...)`
- **Problème :** L'appel système direct suppose la présence de `systemctl` (environnement Linux Debian), impactant la portabilité.
- **Action requise :** Valider la présence de l'outil ou intercepter gracieusement l'erreur de commande introuvable.

### [G-05] Appel système ou exécution de commande système en dur
- **Fichier :** [worker/stats.go:186](file:///Users/flavio/Documents/Projets/Youcloud-API/worker/stats.go#L186)
- **Extrait :** `if err := syscall.Statfs("/", &stat); err != nil {`
- **Problème :** L'appel direct à `syscall.Statfs` restreint la compatibilité multi-plateforme.
- **Action requise :** Prévoir des fallbacks pour les systèmes non-POSIX ou Windows.

### [A-01] Nom de fonction dupliqué dans plusieurs fichiers
- **Fichier :** [master/core/audit.py:177](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/audit.py#L177) et `master/api/nodes.py:364`
- **Extrait :** `async def verify_chain`
- **Problème :** Deux fonctions homonymes existent dans des modules séparés (Core vs API), augmentant le risque de confusion et d'erreurs d'import.
- **Action requise :** Différencier les noms, par ex. renommer l'API en `verify_audit_chain`.

### [A-02] Commentaire didactique paraphrase le code
- **Fichier :** [master/core/secret_loader.py:68](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/secret_loader.py#L68)
- **Extrait :** `# Not configured — return empty string (caller decides if required)`
- **Problème :** Le commentaire répète textuellement la logique triviale implémentée.
- **Action requise :** Retirer les commentaires redondants.

### [A-07] Dicts/caches sans TTL ou cleanup
- **Fichier :** [master/core/node_manager.py:126](file:///Users/flavio/Documents/Projets/Youcloud-API/master/core/node_manager.py#L126)
- **Extrait :** `self._pending_intents: dict[str, asyncio.Future] = {}`
- **Problème :** Ce dictionnaire stocke des requêtes WebSocket en cours. Si des requêtes échouent sans émettre de réponse, elles restent indéfiniment en mémoire.
- **Action requise :** Implémenter une routine de nettoyage périodique (garbage collection des futures expirés).

### [P-01] Prompts non versionnés
- **Fichier :** [master/api/chat.py:147](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L147)
- **Extrait :** `system_prompt = await _build_chat_context(...)`
- **Problème :** Les instructions systèmes de l'IA sont construites de manière dynamique via du code Python, empêchant le versionnage et le test isolé des prompts.
- **Action requise :** Centraliser les prompts dans des fichiers Markdown versionnés.

### [P-02] Paramètres modèle hardcodés
- **Fichier :** [master/api/chat.py:157](file:///Users/flavio/Documents/Projets/Youcloud-API/master/api/chat.py#L157)
- **Extrait :** `async for event in llm.stream(messages, temperature=0.3):`
- **Problème :** La `temperature` est configurée en dur directement dans l'appel d'API.
- **Action requise :** Exposer ce paramètre dans la configuration (`settings`).

### [S-02] Colonnes status sans contrainte CHECK
- **Fichier :** [master/db/alembic/versions/001_initial_schema.py:145](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/alembic/versions/001_initial_schema.py#L145)
- **Extrait :** `sa.Column("status", sa.String(), nullable=False, server_default="PENDING")`
- **Problème :** La colonne stocke un état textuel sans contrainte d'intégrité au niveau DB, ce qui peut mener à des états invalides ou incohérents.
- **Action requise :** Définir une contrainte CHECK restreignant les valeurs permises (PENDING, APPROVED, REJECTED, EXECUTED, FAILED).

### [S-03] ALTER TABLE sans DEFAULT
- **Fichier :** [master/db/migrations.py:48](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/migrations.py#L48)
- **Extrait :** `await db.execute("ALTER TABLE nodes ADD COLUMN insight_profile TEXT")`
- **Problème :** L'ajout de colonnes sans valeur par défaut (DEFAULT) sur des tables existantes peut provoquer des incohérences lors des migrations.
- **Action requise :** Spécifier une valeur par défaut ou initialiser les lignes existantes.

### [X-03] Config hardcodée
- **Fichier :** [master/db/database.py:37](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L37)
- **Extrait :** `conn = await aiosqlite.connect(self._path, timeout=30.0)`
- **Problème :** La valeur de `timeout` de connexion DB est codée en dur.
- **Action requise :** Centraliser dans `config.py`.

### [X-06] Dépendances non whitelistées
- **Fichier :** [requirements.txt](file:///Users/flavio/Documents/Projets/Youcloud-API/requirements.txt)
- **Extrait :** `bcrypt`, `itsdangerous`, `python-multipart`
- **Problème :** Ces dépendances de production sont déclarées mais ne figurent pas dans la liste blanche de base du projet.
- **Action requise :** Valider leur pertinence ou les consigner dans la whitelist officielle.

### [PERF-02] asyncio.Queue sans maxsize
- **Fichier :** [master/db/database.py:25](file:///Users/flavio/Documents/Projets/Youcloud-API/master/db/database.py#L25)
- **Extrait :** `self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()`
- **Problème :** Une file d'attente asynchrone sans paramètre `maxsize` n'a pas de limite supérieure et peut consommer trop de mémoire en cas de saturation de requêtes DB.
- **Action requise :** Définir une taille limite au pool (par exemple, 10 ou 20 connexions).

---

## 📊 Métriques Git

### M-01 : Hot spots (fichiers les plus modifiés)
Les fichiers les plus modifiés de la base de code, nécessitant une surveillance accrue de la complexité :
- `master/api/deps.py` : 10 modifications
- `master/ws/worker_handler.py` : 9 modifications
- `master/main.py` : 9 modifications
- `master/config.py` : 9 modifications
- `master/core/node_manager.py` : 8 modifications
- `master/api/nodes.py` : 8 modifications

### M-02 : Ratio ajout/suppression (dernier sprint)
- **Ratio insertions/suppressions :** `19691 insertions / 15901 suppressions = 1.24` (Seuil d'alerte : 10).
Le ratio est très équilibré, indiquant une saine refactorisation et élimination de code inutile au cours du sprint en cours.

### M-03 : Commits récents sans tests
Commits du sprint 5 modifiant des sources mais n'incluant aucun test unitaire associé :
- ⚠️  `f8e79c7` fix(ci/worker): resolve Go test compilation error and eliminate redundant CI formatting checks
- ⚠️  `a4ed73a` chore(frontend/build): compile production build files and update master/static/
- ⚠️  `8ee37bd` feat(frontend/ui): implement premium layouts, refactor pages and custom UI controls
- ⚠️  `71940d8` style(backend): add noqa F821 for intentional lazy LLM type hints

---

## 🔍 Nécessite revue humaine

### DOC-03 : Tests de régression pour les limitations documentées dans LIMITS.md
Vérifier l'existence et la couverture de tests spécifiques pour valider les comportements limites décrits :
- *Double enrôlement simultané concurrent* (comportement d'exclusion en cas de race condition DB).
- *heartbeat + unregister race condition* (WebSocket coupé en cours de mise à jour de l'état).

### DOC-01 : Écart de documentation des API Routes
- Il y a **42 routes d'API** actives déclarées dans le code sous `master/api/`.
- Cependant, seulement **9 routes clés** sont documentées dans le `README.md`.
- Écart : 33 routes non documentées à intégrer dans la doc d'architecture.

### D-02 : Audit des vulnérabilités de sécurité Python (CVE)
- `pip-audit` n'a pas pu être exécuté automatiquement (exécutable absent de l'environnement).
- Une vérification manuelle des versions déclarées (comme `itsdangerous==2.2.0`, `bcrypt==4.0.1` ou `python-multipart==0.0.20`) doit être programmée.

---

## ✅ Points positifs
- **[T-01] Excellente couverture des modules critiques :** Les tests affichent une couverture globale de **97%** sur la sécurité (`security_manager.py`), l'authentification (`auth.py`) et la DB (`database.py`), dépassant le seuil minimum requis de 95%.
- **[D-01] Versions strictes :** Les versions des dépendances Python dans `requirements.txt` sont toutes épinglées (`==`).
- **[S-01] Idempotence DB :** Toutes les tables sont créées avec la clause d'idempotence `CREATE TABLE IF NOT EXISTS` dans `models.py`.
- **[D-04] Worker standard standardisé :** Le worker utilise strictement le compilateur Go 1.23 standard et sa bibliothèque intégrée (stdlib only), sans importation de dépendances tierces potentiellement vérolées.

---
*Rapport généré par la tâche d'audit automatique.*
*Catalogue de référence : DEBT_CATALOG.md*
*Aucune modification n'a été effectuée dans le code source.*
