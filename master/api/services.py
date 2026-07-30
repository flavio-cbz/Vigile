from __future__ import annotations

"""
Vigile — Services & Containers API

Endpoints for interacting with Worker-managed systemd services and Docker containers.
All operations are performed live via INTENT messages over WebSocket.

Endpoints:
  GET    /api/nodes/{node_id}/services                      Operator+: list services
  GET    /api/nodes/{node_id}/services/{service_name}       Operator+: service status
  POST   /api/nodes/{node_id}/services/{service_name}/restart Admin: restart service
  GET    /api/nodes/{node_id}/containers                    Operator+: list containers
  POST   /api/nodes/{node_id}/containers/{container_id}/restart  Admin: restart container
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel

from master.api.demo_data import (
    DEMO_CONTAINERS,
    DEMO_SERVICES,
    get_demo_node,
    get_demo_service,
    is_demo,
)
from master.api.deps import DB, get_node_manager, require_role
from master.api.rate_limits import WORKER_CONTROL_LIMIT
from master.core.audit import AuditAction, log_action
from master.core.node_manager import NodeManager
from master.core.rate_limiter import rate_limiter
from master.core.worker_query_port import WorkerQueryPort
from master.core.plugin_utils import (
    parse_worker_list,
    parse_worker_object,
)
from master.core.plugin_helpers import (
    parse_container_list,
    parse_service_list,
    parse_service_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nodes/{node_id}", tags=["services"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _get_node_or_404(nm: NodeManager, db: DB, node_id: str) -> dict[str, Any]:
    """Fetch a node or raise 404."""
    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return node


async def _query_intent(
    nm: NodeManager,
    node_id: str,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Send a read-only intent via WorkerQueryPort and handle errors."""
    port = WorkerQueryPort(nm)
    try:
        return await port.query(node_id, action, params, timeout=15.0)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Worker did not respond to {action} request in time",
        )


async def _dispatch_intent(
    nm: NodeManager,
    db: DB,
    node_id: str,
    action: str,
    params: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    """Dispatch a mutating intent via ApprovedProposalDispatcher."""
    from master.core.proposal_dispatcher import ApprovedProposalDispatcher

    dispatcher = ApprovedProposalDispatcher(nm)
    try:
        return await dispatcher.dispatch_admin_action(
            node_id, action, params, user_id, db, intent_timeout=15.0,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Worker did not respond to {action} request in time",
        )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ServiceListResponse(BaseModel):
    node_id: str
    services: list[dict[str, str]]


class ServiceStatusResponse(BaseModel):
    node_id: str
    service: str
    active: str
    enabled: str


class ServiceActionResponse(BaseModel):
    node_id: str
    service: str
    output: str
    error: str | None = None


class ContainerListResponse(BaseModel):
    node_id: str
    containers: list[dict[str, Any]]


class ContainerActionResponse(BaseModel):
    node_id: str
    container_id: str
    output: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Systemd Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/services",
    response_model=ServiceListResponse,
    summary="List systemd services on a node (Operator+)",
    dependencies=[Depends(rate_limiter.dependency(WORKER_CONTROL_LIMIT))],
)
async def list_services(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ServiceListResponse:
    """Fetch the list of all systemd services from a Worker."""
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return ServiceListResponse(node_id=node_id, services=DEMO_SERVICES)

    await _get_node_or_404(nm, db, node_id)
    result = await _query_intent(nm, node_id, "LIST_SERVICES", {})

    services: list[dict[str, str]] = []
    if result.get("success"):
        parsed = parse_service_list(result.get("output", ""))
        if parsed is not None:
            services = parsed
        else:
            logger.warning("Node %s: unparseable service list", node_id)
    else:
        logger.warning("Node %s: LIST_SERVICES failed: %s", node_id, result.get("error", "unknown"))

    return ServiceListResponse(
        node_id=node_id,
        services=services,
    )


@router.get(
    "/services/{service_name}",
    response_model=ServiceStatusResponse,
    summary="Get service status (Operator+)",
    dependencies=[Depends(rate_limiter.dependency(WORKER_CONTROL_LIMIT))],
)
async def get_service_status(
    node_id: Annotated[str, Path(description="Node UUID")],
    service_name: Annotated[str, Path(description="Systemd service name (e.g. ssh.service)")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ServiceStatusResponse:
    """Fetch the status of a specific systemd service on a Worker."""
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        svc = get_demo_service(service_name)
        if svc is not None:
            return ServiceStatusResponse(
                node_id=node_id,
                service=service_name,
                active=svc.get("state", "active"),
                enabled=svc.get("status", "enabled"),
            )
        return ServiceStatusResponse(
            node_id=node_id,
            service=service_name,
            active="unknown",
            enabled="unknown",
        )

    await _get_node_or_404(nm, db, node_id)
    result = await _query_intent(nm, node_id, "STATUS_SERVICE", {"service": service_name})

    if result.get("success"):
        parsed = parse_service_status(result.get("output", ""))
        if parsed is not None:
            return ServiceStatusResponse(node_id=node_id, **parsed)
    else:
        logger.warning(
            "Node %s: STATUS_SERVICE failed: %s", node_id, result.get("error", "unknown")
        )

    return ServiceStatusResponse(
        node_id=node_id,
        service=service_name,
        active="unknown",
        enabled="unknown",
    )


@router.post(
    "/services/{service_name}/restart",
    response_model=ServiceActionResponse,
    summary="Restart a systemd service (Admin only)",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limiter.dependency(WORKER_CONTROL_LIMIT))],
)
async def restart_service(
    node_id: Annotated[str, Path(description="Node UUID")],
    service_name: Annotated[str, Path(description="Systemd service name (e.g. nginx.service)")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ServiceActionResponse:
    """Restart a systemd service on a Worker (requires admin role)."""
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return ServiceActionResponse(
            node_id=node_id,
            service=service_name,
            output=f"Simulated restart of {service_name} completed successfully.",
            error=None,
        )

    await _get_node_or_404(nm, db, node_id)
    result = await _dispatch_intent(nm, db, node_id, "RESTART_SERVICE", {"service": service_name}, claims["sub"])

    if result.get("success"):
        await log_action(
            db,
            user_id=claims["sub"],
            action=AuditAction.RESTART_SERVICE,
            node_id=node_id,
            details={"service_name": service_name},
        )

    return ServiceActionResponse(
        node_id=node_id,
        service=service_name,
        output=result.get("output", ""),
        error=result.get("error") if not result.get("success") else None,
    )


# ---------------------------------------------------------------------------
# Docker Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/containers",
    response_model=ContainerListResponse,
    summary="List Docker containers on a node (Operator+)",
    dependencies=[Depends(rate_limiter.dependency(WORKER_CONTROL_LIMIT))],
)
async def list_containers(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ContainerListResponse:
    """Fetch the list of all Docker containers from a Worker."""
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        node_containers = [c for c in DEMO_CONTAINERS if c.get("node_id") == node_id]
        return ContainerListResponse(node_id=node_id, containers=node_containers)

    await _get_node_or_404(nm, db, node_id)
    result = await _query_intent(nm, node_id, "LIST_CONTAINERS", {})

    containers: list[dict[str, Any]] = []
    if result.get("success"):
        parsed = parse_container_list(result.get("output", ""))
        if parsed is not None:
            containers = parsed
        else:
            logger.warning("Node %s: unparseable container list", node_id)
    else:
        logger.warning(
            "Node %s: LIST_CONTAINERS failed: %s", node_id, result.get("error", "unknown")
        )

    return ContainerListResponse(
        node_id=node_id,
        containers=containers,
    )


@router.post(
    "/containers/{container_id}/restart",
    response_model=ContainerActionResponse,
    summary="Restart a Docker container (Admin only)",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limiter.dependency(WORKER_CONTROL_LIMIT))],
)
async def restart_container(
    node_id: Annotated[str, Path(description="Node UUID")],
    container_id: Annotated[str, Path(description="Container ID or name")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ContainerActionResponse:
    """Restart a Docker container on a Worker (requires admin role)."""
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return ContainerActionResponse(
            node_id=node_id,
            container_id=container_id,
            output=f"Simulated restart of container {container_id} completed successfully.",
            error=None,
        )

    await _get_node_or_404(nm, db, node_id)
    result = await _dispatch_intent(nm, db, node_id, "RESTART_CONTAINER", {"container_id": container_id}, claims["sub"])

    if result.get("success"):
        await log_action(
            db,
            user_id=claims["sub"],
            action=AuditAction.RESTART_CONTAINER,
            node_id=node_id,
            details={"container_id": container_id},
        )

    return ContainerActionResponse(
        node_id=node_id,
        container_id=container_id,
        output=result.get("output", ""),
        error=result.get("error") if not result.get("success") else None,
    )
