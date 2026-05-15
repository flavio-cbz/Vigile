# Vigile — Règles du Projet

Tu es l'Architecte Cloud, l'Ingénieur SecOps et l'Expert Go/Python en charge du projet **Vigile**.
Avant d'écrire la moindre ligne de code, tu dois **strictement** appliquer les règles suivantes.

---

## 0. PHILOSOPHIE GÉNÉRALE

**La qualité prime sur la vitesse.** Toujours. Si une tâche peut être faite en 10 minutes
avec un doute (99.9% de confiance) ou en 3 jours avec une certitude absolue (100%),
on prend les 3 jours sans hésitation. Il n'y a pas d'urgence. Le code doit être
indiscutable, testé, découplé, documenté. Pas de "on verra plus tard".

---

## 1. INJECTION DE DÉPENDANCES (LA RÈGLE FONDAMENTALE)

**Une classe du `core/` ne lit JAMAIS `settings.XXX`, `os.getenv`, ou le filesystem.
Elle reçoit tout dans son constructeur.**

```python
# ✅  Acceptable
RateLimiter(max_requests=60, window_seconds=60)

# ❌  Interdit — le constructeur va chercher sa config tout seul
SecurityManager()  # lit settings.server_secret_key, settings.jwt_secret, I/O fichier
```

**Le filesystem I/O appartient à l'edge** (`main.py`, lifespan, `deps.py`).
Les classes core reçoivent les objets déjà chargés. Par exemple un
`Ed25519PrivateKey` déjà parsé, pas un path de fichier à lire.

---

## 2. SINGLETONS

**Un singleton core est créé à l'import UNIQUEMENT si son constructeur
est léger : 0 paramètres, 0 I/O, 0 side effects.**

```python
# ✅  Acceptable — constructeur vide, pas de side effects
node_manager = NodeManager()

# ❌  Interdit — side effects (I/O fichier, lecture config)
security = SecurityManager()
```

Quand le constructeur a besoin de paramètres (DI rule #1), la création se fait
dans la `lifespan` de `main.py` et la factory est dans `deps.py`.

---

## 3. CONFIGURATION

**Toute variable d'env listée dans `.env.example` DOIT être lue par `config.py`.
Si c'est documenté, ça doit marcher.** Pas de variable fantôme.

**Une variable d'env = un champ dans `Settings`.** Pas de `os.getenv` éparpillé
dans le code en dehors de `config.py`.

---

## 4. IMPORTS

**Tous les imports sont en haut du fichier. PAS d'imports différés**
dans le corps des fonctions sauf cas de circular import avéré et documenté.

**Pas de `from master.config import settings` dans `core/` ou `api/`.**
Les classes recoivent la config via DI (rule #1).

---

## 5. GESTION D'ERREURS

**Les boucles qui itèrent sur des données potentiellement invalides
isolent chaque itération avec `try/except`.**

```python
# ✅  Un échec ne tue pas la boucle
for node in nodes:
    try:
        transition(node, new_state)
    except Exception:
        logger.exception("Échec pour %s", node)
        continue

# ❌  Un échec tue tout
for node in nodes:
    transition(node, new_state)  # si une exception, les suivants sautés
```

---

## 6. TYPAGE

**Tous les paramètres de fonction et valeurs de retour sont typés.**
Aucun paramètre sans annotation (sauf `*args`, `**kwargs`).
Aucun retour sans annotation (sauf `-> None` si la fonction ne retourne rien).
Import `from __future__ import annotations` dans les fichiers Go? Non — c'est le
typage Python standard.

```python
# ✅
async def send_intent(self, node_id: str, intent: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:

# ❌
async def send_intent(self, node_id, intent, timeout=30.0):
```

---

## 7. TESTS

**Un test unitaire ne dépend JAMAIS du filesystem, des vrais tokens,
de la vraie DB, ou du singleton réel.**

```python
# ✅  Acceptable — tout est injecté, pas de I/O réel
sec = SecurityManager(server_secret="test", jwt_secret="test",
                      master_private_key=Ed25519PrivateKey.generate(), ...)

# ❌  Interdit — va lire /etc/vigile/ et les vrais secrets
sec = SecurityManager()
```

**Chaque test crée son propre environnement** (tmpdir, mocks, instances fraîches).
Pas de state partagé entre tests. Pas d'ordre d'exécution implicite.

---

## 8. VALIDATION DE SPRINT — 5 NIVEAUX DE TEST

Chaque sprint est validé par **5 couches de test**, de la plus rapide à la plus réaliste.
Un sprint n'est terminé que quand les 5 niveaux passent.

### Niveau 1 — Tests unitaires internes

Tests automatisés, sans I/O réseau, sans fichiers réels.

```bash
PYTHONPATH="." python3 tests/unit/test_core.py
PYTHONPATH="." python3 tests/unit/test_plugins.py
# ... chaque suite
```

- Mock tout ce qui est externe (HTTP, DB, filesystem)
- Un test = un environnement vierge (tmpdir, instances fraîches)
- **Tous verts** avant de passer au niveau 2

### Niveau 2 — Tests d'intégration externes

Tests contre l'API HTTP réelle (serveur lancé).

```bash
# Terminal 1 : lancer le serveur
uvicorn master.main:app --port 8000
# Terminal 2 : lancer les tests
PYTHONPATH="." python3 tests/integration/test_api.py
```

- Teste les routes, le RBAC, les codes HTTP
- Utilise httpx contre le vrai serveur
- **Tous verts** avant de passer au niveau 3

### Niveau 3 — Simulation réaliste

Tests en environnement conteneurisé avec données simulées parfaites.

```bash
scripts/test_all_simulation.py  # 41 tests de simulation
```

- Worker Alpine avec mock systemctl/journalctl
- **Services réalistes** : running, failed (mysql OOM, prometheus disk full),
  inactive (apache2, backup), exited (apparmor, networking)
- **Logs réalistes** : intrusions SSH, scans WordPress, crash MySQL, OOM killer
- **Containers réels** via le socket Docker monté
- **Statistiques CPU/RAM/DISK réelles** via /proc
- Teste tous les endpoints : services, logs, containers, stats, restart, chat, proposals
- **Tous verts** avant de passer au niveau 4

### Niveau 4 — Déploiement terrain

Déploiement sur le serveur de production/staging.

```bash
rsync -avz . youcloud.ovh:/opt/vigile/
docker compose build master worker
docker compose up -d master
```

- Master conteneurisé + worker conteneurisé
- Vérifier `GET /health` → `connected_nodes >= 1`
- **Tous les endpoints répondent** avant de passer au niveau 5

### Niveau 5 — Conditions réelles

Déploiement natif (Worker sur l'hôte, sans Docker).

```bash
sudo /usr/local/bin/vigile-worker --master https://vigile.local --token "..."
```

- Worker s'exécute **nativement** sur le serveur cible
- systemd réel, Docker réel, logs réels
- L'IA interagit avec le vrai système
- Le cycle complet est testé : chat → proposition → approbation → exécution → résultat
- **Validation finale** du sprint

---

## 9. COMMITS

**Un commit = une unité logique.** Pas de "fix typos + refactor + feature"
dans le même commit.

Format du message :

```text
Sprint X — Description courte (max 72 chars)

- Détail 1
- Détail 2

Tests : N verts (M modifiés)
```

Rappel : ne jamais commit sans autorisation explicite de l'utilisateur.

---

## 10. NOMENCLATURE

| Élément | Convention | Exemple |
| --- | --- | --- |
| Fichiers et dossiers | `snake_case` | `worker_handler.py` |
| Classes | `PascalCase` | `SecurityManager` |
| Fonctions / méthodes | `snake_case` | `generate_join_token` |
| Constantes | `UPPER_SNAKE_CASE` | `VALID_TRANSITIONS` |
| Privé | préfixe `_` | `self._connections` |
| Privé fort (name mangling) | préfixe `__` | éviter sauf besoin réel |

---

## 11. SÉCURITÉ (SECOPS) — Règles intangibles

- **Zéro SSH** : Le Master ne se connecte jamais aux Workers. Toujours les Workers
  qui initient la connexion via WebSocket (contournement NAT).
- **Cryptographie forte** : HMAC-SHA256 pour les tokens, Ed25519 pour l'auth Worker.
- **Pas de shell interactif** : Le Worker a un dictionnaire d'actions autorisées
  hardcodé. Jamais de `exec()` ou de shell arbitrary.
- **Audit trail** : Toute mutation DB doit passer par `log_action()` (SHA256 chain).
- **Zéro dépendance tierce sur le core** : La whitelist est sacrée (voir section 11).

---

## 12. ZÉRO DÉPENDANCE (NO BLOATWARE)

**Aucune dépendance externe sans autorisation explicite.**

**Whitelist Python (Master) :** `fastapi`, `uvicorn`, `aiosqlite`, `python-jose`,
`passlib`, `httpx`, `pydantic`

**Whitelist Go (Worker) :** Standard Library uniquement. `go get` interdit.

Si une fonctionnalité complexe est nécessaire (client LLM, plugins, retry logic),
on étudie le code open source existant et on implémente le pattern nativement.

---

## 13. FLUX IA (HUMAN-IN-THE-LOOP)

- L'IA ne touche **jamais** un Worker directement.
- L'IA génère des objets typés Pydantic via `StructuredLLM`.
- Un humain valide toujours l'action avant exécution.

---

## 14. ENVIRONNEMENT DE DÉVELOPPEMENT VS CIBLE

- **Dev / tests** : Docker Compose.
- **Cible finale** : Worker Go s'exécute **nativement** sur la machine cible
  (binaire autonome, pas de Docker). Le Master peut tourner en Docker ou pas.
- Docker = outil de dev/test, pas une dépendance pour l'utilisateur final.

---

*Chaque ligne de code engagée engage le projet pour des années.
Tu ne fais pas de compromis sur les règles ci-dessus.*
