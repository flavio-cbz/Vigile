from __future__ import annotations

"""
Vigile — Per-Endpoint Rate Limit Constants

Centralised limit values for FastAPI dependency-based rate limiting.
Each limit is applied via `Depends(rate_limiter.dependency(N))` on a route.

The global middleware provides a backstop at 300 req/min per IP per route.
The dependency() factory prefixes its bucket key with "dep:" to avoid
bucket sharing (double-counting) with the global middleware.

NOTE: Limits are per-IP per endpoint unless a user-aware key is used.
      Worker control endpoints currently use per-IP limits as a simplification.
"""

# ── Authentication ───────────────────────────────────────────────────────────
# Brute-force protection: login uses a low limit per IP.
LOGIN_LIMIT = 5  # POST /api/auth/login         — 5 req/min per IP
REFRESH_LIMIT = 30  # POST /api/auth/refresh       — 30 req/min per IP

# ── Node Enrollment Scripts ──────────────────────────────────────────────────
# Public endpoints — low limit to prevent abuse as DDoS vectors.
KICKSTART_LIMIT = 10  # GET  /api/nodes/kickstart.sh  — 10 req/min per IP
GENERATE_JOIN_LIMIT = 10  # POST /api/nodes/generate-join — 10 req/min per IP

# ── Worker Control (Service / Container operations) ──────────────────────────
# Per-IP limit. A true per-user limit would require a JWT-aware bucket key.
WORKER_CONTROL_LIMIT = 100  # GET/POST /api/nodes/{node_id}/services/... — 100 req/min per IP

# ── LLM Chat ─────────────────────────────────────────────────────────────────
# Chat endpoints are expensive (LLM inference) — keep the limit moderate.
CHAT_LIMIT = 30  # POST /api/chat               — 30 req/min per IP

# ── Admin ────────────────────────────────────────────────────────────────────
# Higher limit for admin operations. Still constrained to prevent runaway scripts.
ADMIN_LIMIT = 200  # /api/admin/*                 — 200 req/min per IP

# ── Global Middleware Backstop ───────────────────────────────────────────────
GLOBAL_LIMIT = 300  # Applied by rate_limiter.middleware(app) in main.py
