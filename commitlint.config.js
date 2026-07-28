// commitlint.config.js — Application des conventions de commit Vigile
// https://commitlint.js.org/
//
// Basé sur Conventional Commits (https://www.conventionalcommits.org/)
// Adapté à la structure modulaire de Vigile.

module.exports = {
  extends: ["@commitlint/config-conventional"],

  rules: {
    // ── Type ──────────────────────────────────────────────
    "type-enum": [
      2,
      "always",
      [
        "feat",     // Nouvelle fonctionnalité
        "fix",      // Correction de bug
        "docs",     // Documentation uniquement
        "style",    // Formatage, pas de changement de code
        "refactor", // Restructuration sans feature/fix
        "perf",     // Amélioration de performance
        "test",     // Ajout ou mise à jour de tests
        "build",    // Système de build ou dépendances
        "ci",       // Configuration CI/CD
        "chore",    // Tâches de maintenance
        "revert",   // Annuler un commit précédent
      ],
    ],
    "type-case": [2, "always", "lower-case"],
    "type-empty": [2, "never"],

    // ── Scope ─────────────────────────────────────────────
    "scope-enum": [
      1, // AVERTISSEMENT (pas bloquant) — autorise les nouveaux scopes avec un rappel
      "always",
      [
        "master",        // Serveur FastAPI (Python)
        "worker",        // Agent Go
        "frontend",      // SPA React
        "worker-binary", // Distribution binaire / manifest
        "kickstart",     // Script d'installation
        "plugins",       // Système de plugins
        "api",           // Couche REST API
        "ci",            // Pipeline CI/CD
        "docs",          // Documentation
        "ws",            // Protocole WebSocket
        "db",            // Base de données / migrations
        "core",          // Logique métier
        "schemas",       // Schémas Pydantic
        "scripts",       // Scripts de dev / simulation
        "docker",        // Docker / compose
        "tests",         // Suite de tests
        "git",           // Configuration git
        "logging",       // Système de logging
        "security",      // Sécurité / auth / crypto
        "alerts",        // Moteur d'alertes
        "automations",   // Moteur d'automatisation
        "insights",      // Analyse d'anomalies
      ],
    ],
    "scope-case": [2, "always", "lower-case"],

    // ── Sujet ─────────────────────────────────────────────
    "subject-case": [
      2,
      "never",
      ["start-case", "pascal-case", "upper-case"],
    ],
    "subject-empty": [2, "never"],
    "subject-full-stop": [2, "never", "."],

    // ── En-tête (type + scope + sujet) ────────────────────
    "header-max-length": [2, "always", 100],

    // ── Corps ─────────────────────────────────────────────
    "body-leading-blank": [2, "always"],
    "body-max-line-length": [2, "always", 120],

    // ── Pied de page ──────────────────────────────────────
    "footer-leading-blank": [2, "always"],
    "footer-max-line-length": [2, "always", 120],

    // ── Références ────────────────────────────────────────
    // Autorise "Closes #123", "Fixes #456", "Refs #789"
    "references-empty": [1, "never"], // AVERTISSEMENT — encourage les références aux issues
  },
};
