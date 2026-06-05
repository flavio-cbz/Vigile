# Rotation des secrets Vigile

## Clé API LLM compromise

La clé `sk-hY0lH32Z1UDArBSXxUsoyw` est marquée comme compromise dans le rapport d'audit.
Elle fonctionne encore mais DOIT être remplacée immédiatement.

### Procédure

1. **Identifier le provider LLM** — regarde `LLM_BASE_URL` dans `.env` :
   - `api.openai.com` → https://platform.openai.com/api-keys
   - `api.anthropic.com` → https://console.anthropic.com/settings/keys
   - `chat.youcloud.ovh` → dashboard du proxy LLM auto-hébergé

2. **Révoquer l'ancienne clé** `sk-hY0lH32Z1UDArBSXxUsoyw` sur le dashboard du provider

3. **Générer une nouvelle clé** sur le dashboard du provider

4. **Mettre à jour `.env`** :
   ```
   LLM_API_KEY=<nouvelle_clé>
   ```
   Le fichier est dans `.gitignore` — pas de risque de commit accidentel.

5. **Redémarrer le Master** pour prendre en compte la nouvelle clé

### Vérification

```bash
curl -X POST http://localhost:8000/api/chat/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(votre_token)" \
  -d '{"message":"test"}'
```

### Alternative : Docker secrets (production)

```yaml
# docker-compose.yml
services:
  master:
    environment:
      - LLM_API_KEY_FILE=/run/secrets/llm_api_key
    secrets:
      - llm_api_key
secrets:
  llm_api_key:
    file: ./secrets/llm_api_key.txt
```

Supporté nativement par `master/core/secret_loader.py` (commit a7635ea).
