# Déploiement du Worker Vigile

Ce document explique comment le binaire Worker est construit, signé et distribué.

## Principe

Le Master ne redistribue pas directement un binaire Worker embarqué. Il télécharge le binaire approprié depuis **GitHub Releases**, vérifie sa signature **minisign (Ed25519)**, puis le sert au serveur cible via le script `kickstart.sh`.

## Fichiers importants

| Fichier | Rôle |
|---------|------|
| `.github/workflows/release-worker.yml` | CI GitHub Actions : compile, signe et publie les binaires |
| `.github/scripts/generate_manifest.py` | Génère le `manifest.json` d'une release |
| `revoked-versions.json` | Liste des versions révoquées |
| `master/api/worker_binary.py` | Endpoints Master servant les binaires |
| `data/vigile.minisign.pub` | Clé publique minisign (local, non commitée) |
| `data/vigile.minisign.key` | Clé secrète minisign (local, non commitée, **garder secrète**) |

## Prérequis

Le Master utilise le CLI `minisign` pour vérifier les signatures des binaires. Assure-toi qu'il est installé sur le serveur Master :

```bash
# Debian/Ubuntu
apt-get install -y minisign

# macOS
brew install minisign
```

En production via Docker, `minisign` est déjà installé dans `Dockerfile.master`.

## Configuration requise

### 1. Secret GitHub

Ajoute un secret dans **Settings → Secrets and variables → Actions** :

- **Name** : `MINISIGN_SECRET_KEY`
- **Value** : le contenu complet du fichier `data/vigile.minisign.key`

> Ce fichier est gitignoré. Ne le committe jamais. En production, seule la clé publique est nécessaire sur le Master.

### 2. Accès aux releases (repo privé)

Si le dépôt GitHub est **privé**, le Master doit s'authentifier pour télécharger les assets. Crée un Personal Access Token (classic) avec le scope `repo`, puis définis :

```bash
WORKER_BINARY_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

Pour le développement local, tu peux utiliser le token de `gh` :

```bash
export WORKER_BINARY_GITHUB_TOKEN=$(gh auth token)
```

Si le dépôt est public, laisse cette variable vide.

### 3. Variable d'environnement Master

Sur le serveur Master, définis au minimum :

```bash
WORKER_BINARY_PUBLIC_KEY=RWT+mYY8j2fYe5RBquJ1QLm8iEenxrZrvT7cXbTJFXyRyvjWqBU3d6ka
```

Pour le développement local, cette valeur est déjà dans le fichier `.env`.

## Faire une release

```bash
git tag v0.7.0
git push origin v0.7.0
```

GitHub Actions compilera automatiquement 8 binaires :

- linux : amd64, arm64, armv7
- darwin : amd64, arm64
- freebsd : amd64, arm64, armv7

Puis publiera sur GitHub Releases :

- `worker-{os}-{arch}`
- `worker-{os}-{arch}.sha256`
- `worker-{os}-{arch}.sig`
- `manifest.json`
- `revoked-versions.json`

## Endpoints Master

| Endpoint | Description |
|----------|-------------|
| `GET /api/nodes/kickstart.sh` | Script d'installation |
| `GET /api/nodes/binary/{os}/{arch}/worker` | Binaire Worker |
| `GET /api/nodes/binary/{os}/{arch}/worker.sha256` | Empreinte SHA256 |
| `GET /api/nodes/binary/manifest.json` | Manifeste de release |
| `GET /api/nodes/binary/public-key` | Clé publique de vérification |
| `GET /api/admin/binary/refresh` | Force le rafraîchissement du cache (admin) |

## Révocation d'une version

1. Ajoute la version dans `revoked-versions.json` :

```json
{
  "revoked": ["v0.5.0"],
  "revoked_at": {
    "v0.5.0": "2026-06-25T12:00:00Z"
  }
}
```

2. Commit et pousse sur `master`.
3. Attends le TTL (5 minutes par défaut) ou force le rafraîchissement :

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/binary/refresh
```

## Exécuter le Worker manuellement

```bash
# Avec les flags CLI
vigile-worker --master https://master.example.com --token <JOIN_TOKEN>

# Ou avec les variables d'environnement
export MASTER_URL=https://master.example.com
export JOIN_TOKEN=<JOIN_TOKEN>
vigile-worker

# Clés et token dans un répertoire personnalisé (utile pour les tests non-root)
vigile-worker --key-dir ./vigile-data
```

## Dépannage

- **502 Bad Gateway** : le Master ne trouve pas le `manifest.json` sur GitHub Releases.
  - Vérifie que le tag a bien déclenché la CI et que la release contient `manifest.json`.
  - Si le dépôt est privé, vérifie que `WORKER_BINARY_GITHUB_TOKEN` est défini et possède le scope `repo`.
- **Erreur de signature** : vérifie que `WORKER_BINARY_PUBLIC_KEY` correspond bien à la clé utilisée pour signer en CI.
- **Clé secrète manquante** : vérifie le secret `MINISIGN_SECRET_KEY` dans les paramètres GitHub.
- **403 Resource not accessible** en CI : vérifie que le workflow a la permission `contents: write` (voir `.github/workflows/release-worker.yml`).
- **Permission denied sur /etc/vigile** : utilise `--key-dir` pour pointer vers un répertoire accessible en écriture.
