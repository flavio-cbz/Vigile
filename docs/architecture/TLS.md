# TLS / HTTPS — Configuration

## Architecture

```
Client (browser, worker, curl)
        │
        │  HTTPS (port 443)   ───  TLS termination
        ▼
    ┌───────┐
    │ Caddy │  ←  Reverse proxy with auto-TLS (Let's Encrypt or internal CA)
    └───┬───┘
        │
        │  HTTP (port 8000)   ───  Internal Docker network only
        ▼
    ┌───────┐
    │Master │  FastAPI (uvicorn)
    └───────┘
```

- **Caddy** termine le TLS en front du Master.
- **Master** écoute uniquement en HTTP sur le réseau Docker interne (`master:8000`).
- **Worker** se connecte en `wss://` à Caddy (port 443).
- **Healthcheck** du Master continue à fonctionner sur `localhost:8000` (interne conteneur).

## Dev Mode (par défaut)

En développement, Caddy utilise l'issuer `internal` qui génère des certificats auto-signés
au runtime (aucun fichier à fournir).

```bash
docker compose up -d caddy master
curl -sk https://localhost:443/health   # -k pour ignorer le cert auto-signé
```

Le Worker utilise `ALLOW_INSECURE=true` pour accepter le certificat auto-signé de Caddy
sur le réseau Docker interne. **Ne pas utiliser `ALLOW_INSECURE=true` en production.**

### test

```bash
# Vérifier que Caddy répond en HTTPS
curl -sk https://localhost:443/health
# Doit retourner: {"status":"ok"} (ou équivalent)

# Vérifier le HTTP→HTTPS redirect
curl -sI http://localhost:80/health | head -1
# Doit retourner: HTTP/1.1 308 Permanent Redirect
```

## Prod Mode

Pour la production, remplacer `tls internal` par un domaine réel :

1. Modifier `docker/Caddyfile` :

```caddyfile
:443 {
    tls votre-domaine.com  # Let's Encrypt ACME
    reverse_proxy master:8000
}
```

2. (Optionnel) Configurer un challenge DNS pour les wildcards/domaines internes :

```caddyfile
{
    acme_dns cloudflare <api-token>
}
```

3. Redémarrer Caddy :

```bash
docker compose up -d caddy
```

4. Retirer `ALLOW_INSECURE=true` du Worker (il utilisera le CA system trust).

### Let's Encrypt Staging

Pour tester sans rate-limit, ajouter :

```caddyfile
{
    acme_ca https://acme-staging-v02.api.letsencrypt.org/directory
}
```

## Worker TLS

Le Worker Go supporte :
- **`wss://`** — TLS avec vérification du certificat (par défaut)
- **`ALLOW_INSECURE=true`** — désactive la vérification TLS (dev only)

### Rotations de certificats

Caddy gère automatiquement le renouvellement des certificats Let's Encrypt.
Les certificats auto-signés (`internal`) sont regénérés au démarrage.

Pour forcer une rotation en dev :

```bash
docker compose exec caddy caddy renew --force
# ou
docker compose restart caddy
```

## Dépannage

| Symptôme | Cause probable | Solution |
|----------|---------------|----------|
| `curl: (60) SSL certificate problem` | Certificat auto-signé | Ajouter `-k` ou utiliser `ALLOW_INSECURE=true` |
| `connection refused` sur port 443 | Caddy pas encore prêt | Vérifier `docker compose logs caddy` |
| `x509: certificate is valid for...` | Hostname non inclus dans le cert | Ajouter le hostname dans le site block Caddyfile |
| Worker refuse de se connecter | Certificat invalide | Vérifier `ALLOW_INSECURE=true` en dev |
| Let's Encrypt rate-limit | Trop de requêtes | Utiliser `acme_ca staging` pour les tests |
