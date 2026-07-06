# Vigile — Guide de Développement du SDK de Plugins

Ce guide détaille l'architecture du système d'extensions de Vigile et explique comment écrire, tester, et déployer des plugins personnalisés.

---

## 📐 Architecture du Système d'Extensions

Les extensions dans Vigile s'articulent autour de deux concepts majeurs :
1. **Les Hooks (Événements)** : Points d'ancrage déclarés par le Master ou d'autres extensions (ex. `normalize_status_report`, `on_status_report`).
2. **La Sandbox (Sous-processus)** : Par défaut en production, chaque plugin s'exécute dans son propre sous-processus Python isolé. Il communique avec le Master via un protocole IPC JSON-RPC standard (stdin/stdout).

```
┌─────────────────┐                     ┌──────────────────────────┐
│  MASTER NODE    │ ──(stdin: JSON)───> │  PLUGIN WORKER PROCESS   │
│  - FastAPI      │                     │  - Chargement du fichier  │
│  - DB SQL       │ <──(stdout: JSON)── │  - Exécution des Hooks   │
└─────────────────┘                     └──────────────────────────┘
```

---

## 🛠️ Créer une Extension Pas à Pas

Une extension Vigile est un simple fichier Python (ex: `my_alert.py`) qui doit respecter un contrat minimal :
- Exposer une fonction `register(pm)` pour déclarer ses écoutes sur les hooks.
- Exposer éventuellement une fonction `get_config_schema()` pour déclarer ses paramètres de configuration (schéma JSON).

### 1. Structure Minimale d'un Plugin

Voici le code pour un plugin d'alerting basique (`custom_alert.py`) :

```python
import json
import sys
from typing import Any

def register(pm) -> None:
    """
    Méthode d'enregistrement appelée au chargement du plugin.
    Associe des fonctions locales aux hooks globaux du système.
    """
    pm.register("on_status_report", _on_status_report, plugin_name="custom_alert")

def get_config_schema() -> dict[str, Any]:
    """
    Définit les paramètres de configuration exposés dans l'interface UI.
    """
    return {
        "name": "Custom Alerts",
        "description": "Envoie des alertes si les seuils de CPU ou de Mémoire sont dépassés.",
        "category": "Notifications",
        "schema": {
            "email_target": {
                "type": "string",
                "title": "Email de contact",
                "default": "admin@local.host",
            },
            "cpu_limit": {
                "type": "integer",
                "title": "Limite CPU (%)",
                "default": 85,
            }
        }
    }

async def _on_status_report(node_id: str, snapshot: dict, db=None) -> None:
    """
    Exécutée à chaque rapport d'état envoyé par un Worker.
    """
    if not db:
        return

    # Récupérer la configuration définie par l'utilisateur
    cursor = await db.execute(
        "SELECT config_json FROM plugin_configs WHERE plugin_id = 'custom_alert'"
    )
    row = await cursor.fetchone()
    if not row:
        return
    config = json.loads(row["config_json"])

    email = config.get("email_target", "admin@local.host")
    cpu_limit = config.get("cpu_limit", 85)

    cpu = snapshot.get("cpu_percent", 0.0)
    if cpu > cpu_limit:
        # Journalisation sur stderr (sécurisée pour la sandbox)
        print(f"[custom_alert] ALERTE : Le CPU de {node_id} est à {cpu}% ! Notification envoyée à {email}", file=sys.stderr)
```

---

## 🔒 Règles Cruciales de la Sandbox (Sous-processus)

Lorsque le mode sandbox est actif (par défaut) :

### 1. Journalisation (Logs)
N'utilisez **jamais** de `print()` standard ou d'écritures directes sur `sys.stdout`. La sortie standard est réservée à l'IPC JSON-RPC. Si vous corrompez `stdout`, le Master ne pourra plus communiquer avec votre plugin et le déclarera en erreur.
- **Règle** : Écrivez toujours vos logs sur la sortie d'erreur standard : `print("mon log", file=sys.stderr)` ou utilisez le module de logging Python standard (déjà redirigé vers stderr par Vigile).

### 2. Accès à la Base de Données (DB Proxy)
Vous ne pouvez pas partager de connexions SQLite en mémoire avec le processus principal. Vigile fournit un objet proxy `db` transparent dans les arguments de vos hooks.
- Les méthodes supportées sont asynchrones : `await db.execute(sql, params)` et `await db.commit()`.
- Les objets retournés par `execute` sont des proxies de curseur supportant `await cursor.fetchone()`, `await cursor.fetchall()` et l'itération asynchrone `async for row in cursor:`.
- **Note** : Les lignes retournées sont converties en dictionnaires Python natifs. Accédez aux colonnes par leur clé : `row["config_json"]`.

---

## 🧪 Tester une Extension

Pour tester le bon comportement de votre extension localement, vous pouvez écrire un test unitaire pytest :

```python
import json
import pytest
import aiosqlite
from master.core.plugin_manager import PluginManager
from master.plugins.custom_alert import register as register_custom

@pytest.mark.asyncio
async def test_custom_alert_logic(db: aiosqlite.Connection):
    # Activer l'extension en base de données
    await db.execute(
        "INSERT INTO plugin_configs (plugin_id, enabled, config_json) VALUES (?, 1, ?)",
        ("custom_alert", json.dumps({"email_target": "test@domain.com", "cpu_limit": 50}))
    )
    await db.commit()

    pm = PluginManager()
    await pm.initialize(db, sandbox=False) # Désactiver la sandbox pour tester en mémoire
    register_custom(pm)

    # Simuler le déclenchement
    snapshot = {"cpu_percent": 75.0, "mem_percent": 30.0}
    # Appeler le hook et vérifier le comportement attendu
    await pm.async_call("on_status_report", node_id="srv-01", snapshot=snapshot, db=db)
```

Run test suite:
```bash
PYTHONPATH="." pytest tests/test_my_plugin.py -v
```

---

## 🚀 Déploiement

Pour charger votre plugin sur un serveur Vigile de production :
1. Accédez à l'interface d'administration Vigile $\rightarrow$ Section **Extensions**.
2. Cliquez sur **Téléverser une extension (.py)**.
3. Vigile va compiler le code pour valider sa syntaxe, vérifier l'existence de la fonction `register(pm)` avec l'arbre syntaxique AST, écrire le fichier dans `settings.plugins_dir`, l'inscrire en base de données, et l'exécuter dans son sous-processus isolé.
4. Configurez-le directement depuis l'UI via le formulaire généré automatiquement à partir de votre `get_config_schema()`.
