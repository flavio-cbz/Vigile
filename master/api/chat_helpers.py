"""
Vigile — Chat API: shared helper functions

Security helpers, context builder, container target resolution, proposal helpers.
"""

from __future__ import annotations

import json
import logging
import re
import time
from difflib import SequenceMatcher
from typing import Any

from master.api.deps import DB
from master.core.action_proposal import ActionProposal
from master.core.node_manager import NodeManager
from master.core.structured_llm import StructuredLLM

logger = logging.getLogger(__name__)

# --- Security limits ---
MAX_MESSAGE_LENGTH = 10000
MAX_HISTORY_SIZE = 100

# Whitelist of allowed log file paths for the read_logs tool
ALLOWED_LOG_PATHS: tuple[str, ...] = (
    "/var/log/syslog",
    "/var/log/messages",
    "/var/log/auth.log",
    "/var/log/kern.log",
    "/var/log/dpkg.log",
    "/var/log/apt/history.log",
    "/var/log/nginx/access.log",
    "/var/log/nginx/error.log",
    "/var/log/apache2/access.log",
    "/var/log/apache2/error.log",
    "/var/log/mysql/error.log",
    "/var/log/postgresql/postgresql.log",
)

import master.config


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _sanitize_message(content: Any) -> str:
    """Strip control characters and truncate oversized messages."""
    if not isinstance(content, str):
        return ""
    content = content.strip()
    # Strip control characters except newline, tab, carriage return
    content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", content)
    if len(content) > MAX_MESSAGE_LENGTH:
        content = content[:MAX_MESSAGE_LENGTH] + "..."
    return content


def _cap_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cap conversation history to MAX_HISTORY_SIZE entries (newest preserved)."""
    if len(history) > MAX_HISTORY_SIZE:
        return history[-MAX_HISTORY_SIZE:]
    return history


def _validate_log_path(path: str | None) -> bool:
    """Validate that a log file path is in the allowed whitelist.

    Returns True if path is None (worker-default log), False if path is empty
    or not in the whitelist.
    """
    if path is None:
        return True
    if not path:
        return False
    return path in ALLOWED_LOG_PATHS


# ---------------------------------------------------------------------------
# Chat context builder
# ---------------------------------------------------------------------------


async def _build_chat_context(
    nm: NodeManager, db: DB, node_id: str | None, locale: str = "fr"
) -> str:
    """
    Build a system prompt with node context.
    If no node_id is specified, returns a generic sysadmin prompt.
    """
    from master.core.prompts import load_prompt

    lang_instruction = (
        "You must always reply in English."
        if locale == "en"
        else "Tu dois toujours répondre en français."
    )
    if not node_id or node_id == "all":
        return load_prompt("chat_generic", lang_instruction=lang_instruction)

    node = await nm.get_node(db, node_id)
    if node is None:
        return load_prompt("chat_node_not_found", lang_instruction=lang_instruction)

    # Gather node context
    context_parts = [
        f"Node: {node.get('name', 'unknown')} (ID: {node_id[:8]}...)",
        f"State: {node.get('state', 'unknown')}",
        f"OS: {node.get('os', 'unknown')} / {node.get('arch', 'unknown')}",
        f"Hostname: {node.get('hostname', 'unknown')}",
    ]

    if node.get("state") in ("CONNECTED",):
        context_parts.append("Status: online")

        # Fetch latest stats
        try:
            async with db.execute(
                "SELECT cpu_percent, mem_percent, disk_percent, uptime_seconds "
                "FROM metrics_snapshots WHERE node_id = ? "
                "ORDER BY collected_at DESC LIMIT 1",
                (node_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                context_parts.append(
                    f"CPU: {row['cpu_percent']:.1f}% | "
                    f"RAM: {row['mem_percent']:.1f}% | "
                    f"Disk: {row['disk_percent']:.1f}% | "
                    f"Uptime: {row['uptime_seconds'] / 3600:.0f}h"
                )
        except Exception:
            logger.exception("Failed to build status context for node")

    context_lines = "\n".join(f"- {line}" for line in context_parts)
    return load_prompt(
        "chat_with_context",
        lang_instruction=lang_instruction,
        context_lines=context_lines,
    )


# ---------------------------------------------------------------------------
# Container target resolution (Copilot safety)
# ---------------------------------------------------------------------------

_CONTAINER_TARGET_KEYS = ("container_id", "container", "name", "target", "id")
_FUZZY_CONTAINER_THRESHOLD = 0.75
_FUZZY_CONTAINER_AMBIGUITY_MARGIN = 0.08


async def _normalize_action_proposal(
    db: DB,
    nm: NodeManager,
    proposal: ActionProposal,
) -> str | None:
    """
    Normalize safety-sensitive proposal params before storage/execution.

    Returns an operator-facing error string when the target cannot be resolved
    safely. A non-None value means the caller must not execute the intent.
    """
    if proposal.action != "RESTART_CONTAINER":
        return None

    target = _extract_container_target(proposal.params)
    if not target:
        return "RESTART_CONTAINER requires a container target"

    resolved = await _resolve_container_target(db, nm, proposal.node_id, target)
    if resolved.get("status") == "matched":
        value = resolved["container_id"]
        proposal.params = {"container_id": value, "target": value}
        return None
    if resolved.get("status") == "ambiguous":
        candidates = ", ".join(resolved.get("candidates", []))
        return f"Ambiguous container target '{target}'. Candidates: {candidates}"
    return f"Unknown container target '{target}'"


def _extract_container_target(params: dict[str, Any]) -> str:
    """Return the first non-empty container target from common LLM param names."""
    for key in _CONTAINER_TARGET_KEYS:
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def _resolve_container_target(
    db: DB,
    nm: NodeManager,
    node_id: str,
    target: str,
) -> dict[str, Any]:
    """Resolve a requested container target against cached containers, then live data."""
    cached_containers = await _get_cached_containers(db, node_id)
    if cached_containers:
        cached_match = _match_container(target, cached_containers)
        if cached_match.get("status") != "not_found":
            return cached_match

    live_containers = await _get_live_containers(nm, node_id)
    if live_containers:
        return _match_container(target, live_containers)

    return {"status": "not_found"}


async def _get_cached_containers(db: DB, node_id: str) -> list[dict[str, Any]]:
    """Read the node container cache. Invalid cache data is treated as empty."""
    async with db.execute(
        "SELECT cached_containers_json FROM nodes WHERE id = ?",
        (node_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None or not row["cached_containers_json"]:
        return []
    try:
        raw = json.loads(row["cached_containers_json"])
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


async def _get_live_containers(nm: NodeManager, node_id: str) -> list[dict[str, Any]]:
    """Fetch live containers from the Worker when cache data cannot resolve a target."""
    try:
        result = await nm.send_intent(node_id, {"action": "LIST_CONTAINERS"}, timeout=10.0)
    except (RuntimeError, TimeoutError):
        return []
    if not result.get("success"):
        return []
    from master.core.plugin_utils import parse_worker_list
    from master.plugins.docker_plugin import ContainerSummary
    parsed = parse_worker_list(result.get("output", ""), ContainerSummary)
    return parsed or []


def _match_container(target: str, containers: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a single exact/fuzzy container match, or an ambiguity/not-found marker."""
    normalized_target = _normalize_match_text(target)
    if not normalized_target:
        return {"status": "not_found"}

    exact_matches: list[dict[str, Any]] = []
    for container in containers:
        for variant, value in _container_match_variants(container):
            if normalized_target == variant:
                exact_matches.append({"container_id": value, "display": value})
                break
    if len(exact_matches) == 1:
        return {"status": "matched", **exact_matches[0]}
    if len(exact_matches) > 1:
        return {
            "status": "ambiguous",
            "candidates": [match["display"] for match in exact_matches],
        }

    scored: list[tuple[float, str]] = []
    for container in containers:
        best_score = 0.0
        best_value = ""
        for variant, value in _container_match_variants(container):
            score = SequenceMatcher(None, normalized_target, variant).ratio()
            if score > best_score:
                best_score = score
                best_value = value
        if best_value:
            scored.append((best_score, best_value))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < _FUZZY_CONTAINER_THRESHOLD:
        return {"status": "not_found"}

    top_score, top_value = scored[0]
    ambiguous = [
        value
        for score, value in scored[1:]
        if score >= _FUZZY_CONTAINER_THRESHOLD
        and top_score - score <= _FUZZY_CONTAINER_AMBIGUITY_MARGIN
    ]
    if ambiguous:
        return {"status": "ambiguous", "candidates": [top_value, *ambiguous]}

    return {"status": "matched", "container_id": top_value, "display": top_value}


def _container_match_variants(container: dict[str, Any]) -> list[tuple[str, str]]:
    """Build normalized match strings paired with the value to send to Docker."""
    variants: list[tuple[str, str]] = []

    container_id = str(container.get("id") or "").strip()
    name = str(container.get("name") or "").strip().lstrip("/")
    preferred_name = name or container_id

    if name:
        variants.append((_normalize_match_text(name), preferred_name))
        for part in name.replace("_", "-").replace(".", "-").split("-"):
            normalized_part = _normalize_match_text(part)
            if normalized_part:
                variants.append((normalized_part, preferred_name))
    if container_id:
        variants.append((_normalize_match_text(container_id), container_id))

    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for variant in variants:
        if variant[0] and variant not in seen:
            seen.add(variant)
            unique.append(variant)
    return unique


def _normalize_match_text(value: str) -> str:
    """Normalize operator/LLM text for conservative container matching."""
    return value.strip().lower().lstrip("/")


# ---------------------------------------------------------------------------
# Proposal helpers
# ---------------------------------------------------------------------------


async def _persist_proposal(db: DB, proposal: ActionProposal) -> None:
    """Insert a new action proposal into the database."""
    data = proposal.to_db_dict()
    await db.execute(
        """
        INSERT INTO action_proposals
            (id, node_id, action, params_json, reasoning, risk_level,
             status, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["id"],
            data["node_id"],
            data["action"],
            data["params_json"],
            data["reasoning"],
            data["risk_level"],
            data["status"],
            data["created_by"],
            data["created_at"],
            data["updated_at"],
        ),
    )
    await db.commit()
    logger.info(
        "Proposal created: id=%s action=%s node=%s",
        proposal.id,
        proposal.action,
        proposal.node_id,
    )


def _list_available_actions() -> str:
    return (
        "GET_STATS, READ_LOGS, LIST_SERVICES, STATUS_SERVICE, "
        "RESTART_SERVICE, LIST_CONTAINERS, RESTART_CONTAINER"
    )
