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
from master.core.audit import AuditAction, log_action
from master.core.node_manager import NodeManager
from master.plugins.docker_plugin import parse_container_list
from master.plugins.systemd_plugin import (
    parse_service_list,
    parse_service_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nodes/{node_id}", tags=["services"])

async def _get_node_or_404(nm: NodeManager, db: DB, node_id: str) -> dict[str, Any]:
    node = await nm.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return node


async def _send_intent(
    nm: NodeManager,
    node_id: str,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    try:
        return await nm.send_intent(
            node_id,
            {"action": action, "params": params},
            timeout=15.0,
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

@router.get(
    "/services",
    response_model=ServiceListResponse,
    summary="List systemd services on a node (Operator+)",
)
async def list_services(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ServiceListResponse:
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return ServiceListResponse(node_id=node_id, services=DEMO_SERVICES)

    await _get_node_or_404(nm, db, node_id)
    result = await _send_intent(nm, node_id, "LIST_SERVICES", {})

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
)
async def get_service_status(
    node_id: Annotated[str, Path(description="Node UUID")],
    service_name: Annotated[str, Path(description="Systemd service name (e.g. ssh.service)")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ServiceStatusResponse:
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
    result = await _send_intent(nm, node_id, "STATUS_SERVICE", {"service": service_name})

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
)
async def restart_service(
    node_id: Annotated[str, Path(description="Node UUID")],
    service_name: Annotated[str, Path(description="Systemd service name (e.g. nginx.service)")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ServiceActionResponse:
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return ServiceActionResponse(
            node_id=node_id,
            service=service_name,
            output=f"Simulated restart of {service_name} completed successfully.",
        )

    await _get_node_or_404(nm, db, node_id)
    result = await _send_intent(nm, node_id, "RESTART_SERVICE", {"service": service_name})

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

@router.get(
    "/containers",
    response_model=ContainerListResponse,
    summary="List Docker containers on a node (Operator+)",
)
async def list_containers(
    node_id: Annotated[str, Path(description="Node UUID")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("operator", "admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ContainerListResponse:
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        node_containers = [c for c in DEMO_CONTAINERS if c.get("node_id") == node_id]
        return ContainerListResponse(node_id=node_id, containers=node_containers)

    await _get_node_or_404(nm, db, node_id)
    result = await _send_intent(nm, node_id, "LIST_CONTAINERS", {})

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
)
async def restart_container(
    node_id: Annotated[str, Path(description="Node UUID")],
    container_id: Annotated[str, Path(description="Container ID or name")],
    db: DB,
    claims: Annotated[dict, Depends(require_role("admin"))],
    nm: NodeManager = Depends(get_node_manager),
) -> ContainerActionResponse:
    if is_demo(claims):
        if get_demo_node(node_id) is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return ContainerActionResponse(
            node_id=node_id,
            container_id=container_id,
            output=f"Simulated restart of container {container_id} completed successfully.",
        )

    await _get_node_or_404(nm, db, node_id)
    result = await _send_intent(nm, node_id, "RESTART_CONTAINER", {"container_id": container_id})

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
