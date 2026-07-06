# Fiche de Présentation — Vigile

Cette fiche synthétise la vision, l'architecture et les principes directeurs de **Vigile**. Elle est optimisée pour être utilisée comme instructions de projet (Custom Instructions) pour les assistants IA.

---

## 🎯 Purpose & Context

*   **Contexte personnel** : Flavio est étudiant et gère un homelab sous Debian hébergeant plusieurs conteneurs Docker (Plex, Home Assistant, Radarr, etc.).
*   **Problématique** : Le homelab subit des incidents récurrents (crashes de l'OS, freezes de la box internet, pannes de courant). Ces pannes altèrent l'uptime et nécessitent des interventions manuelles répétitives en SSH, d'où la création de **Vigile**.
*   **Concept & Architecture cible** :
    *   **Master (VPS)** : L'interface et le cerveau décisionnel du système. Construit avec **FastAPI**, **SQLite** (via `aiosqlite`) et sert un frontend en **React SPA** (Vite + TypeScript + Tailwind CSS v4 + Zustand + Recharts). Il embarque un agent LLM pour diagnostiquer et proposer des actions correctives.
    *   **Worker (Go)** : L'agent d'exécution déployé localement dans le homelab. Écrit en **Go (stdlib pure, sans aucune dépendance externe)**. Il n'offre aucun shell interactif à l'IA pour éviter les hallucinations destructrices, mais expose une whitelist d'actions (gestion de services systemd, contrôle de conteneurs Docker via socket Unix, lecture de logs).
    *   **Connexion (WebSocket Reverse)** : C'est le Worker qui établit la connexion WebSocket persistante vers le Master. Cela permet de traverser les pare-feux et NAT sans exposer de port local sur internet.
    *   **Sécurité & Traçabilité** :
        *   Authentification mutuelle par échange de clés cryptographiques **Ed25519** (handshake challenge-response) lors de l'enrôlement.
        *   Jeton d'enrôlement à usage unique validé par **HMAC**.
        *   Journal d'audit append-only sous forme de chaîne de hashs **SHA-256** garantissant l'intégrité de toutes les mutations.
*   **Documentation de référence** :
    *   Description détaillée : `/mnt/project/README.md`
    *   Normes de développement : `/mnt/project/RULES.md`

---

## 🚀 Current State

*   **Phase actuelle** : Phase finale de développement et intégration de la couche **Frontend** en **React SPA**.

---

## 🧠 Key Learnings & Principles

*   **Philosophie UX de Vigile** :
    *   **Abstraction des métriques brutes** : Les chiffres et graphiques de performance bruts (CPU %, RAM MB) ne doivent pas être l'élément principal affiché.
    *   **Langage naturel contextualisé** : Donner la priorité absolue à des diagnostics compréhensibles et prédictifs (ex. : *"Disque plein dans 1 semaine"*, *"Charge CPU élevée — transcodage Plex détecté"*).
    *   **Accès avancé secondaire** : Les métriques brutes restent consultables par l'utilisateur, mais uniquement dans un panneau secondaire ou un onglet de détails.
    *   **Visibilité des insights** : Les recommandations intelligentes générées par l'IA doivent être affichées au-dessus du volet "Tâches Récentes".
    *   **Esprit collaboratif** : Toujours présenter des variantes conceptuelles ou fonctionnelles à Flavio avant d'initier toute intégration.

---

## 🛡️ Approach & Patterns

*   **Normes de développement strictes (définies dans `RULES.md`)** :
    *   **Injection de dépendances (DI)** : Les classes métier du dossier `core/` ne doivent jamais lire les variables d'environnement (`os.getenv`), les fichiers de configuration ou le système de fichiers par elles-mêmes. Toutes les ressources et configurations requises doivent être injectées via leur constructeur.
    *   **Typage strict et complet** : Toutes les signatures de fonctions, méthodes et variables doivent être explicitement annotées.
    *   **Zéro dépendance tierce** : Aucune dépendance en dehors de la whitelist stricte de Python (FastAPI, Uvicorn, aiosqlite, python-jose, passlib, httpx, pydantic) et stdlib Go uniquement pour le Worker.
    *   **Validation rigoureuse (5 niveaux de tests)** : Un incrément n'est considéré comme achevé qu'après succès complet des 5 couches de test (tests unitaires internes, tests d'intégration API, simulation conteneurisée, déploiement sur staging, et tests natifs en conditions réelles).
    *   **Contrôle des versions** : Ne jamais effectuer de commit ou de push vers la branche de développement sans l'accord explicite préalable de Flavio.

---

## 🧰 Tools & Resources

*   **Backend Master** : Python / FastAPI, SQLite (`aiosqlite`).
*   **Frontend Master** : React 19, Vite, TypeScript, Tailwind CSS v4, Zustand, Recharts (généré et servi statiquement depuis `frontend/dist`).
*   **Worker** : Go (stdlib uniquement, contrainte matérielle et logicielle stricte).
*   **Infrastructure** : Système d'exploitation Debian, Docker pour le homelab, VPS pour l'hébergement du Master.
*   **Services homelab cibles** : Plex, Home Assistant, Radarr, etc.
