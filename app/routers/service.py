from __future__ import annotations

import secrets
from collections import defaultdict
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Header

from app.core.logging import get_logger
from app.core.redis import RedisManager, caches
from app.core.security import (
    get_header_api_key,
    validate_authbridge_api_key,
    validate_item_api_key,
    new_system_token,
    check_rate_limit,
)
from app.models import (
    DiscoveryResponse,
    DiscoveredService,
    DiscoveredServiceLink,
    EntityType,
    ServiceEntity,
    ServiceLimited,
    WorkspaceLimited,
)
from app.routers.workspace import get_workspace, reload_workspaces
from app.settings import get_settings

log = get_logger("auth-bridge.service")

router_v1 = APIRouter(prefix="/api/v1", tags=["services"])
router_v2 = APIRouter(prefix="/api/v2", tags=["services-v2"])


async def reload_services(with_log: bool = False) -> None:
    rm = RedisManager()
    await caches.reload_services_if_needed(rm, log_details=with_log)


async def get_service(service_id: str) -> ServiceEntity:
    await reload_services()
    service = caches.services.get(service_id)
    if not service:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "Service not found after [get_service]"})
    return service


async def service_exists(service_id: str) -> bool:
    rm = RedisManager()
    return (await rm.get_item(service_id, EntityType.SERVICE.value)) is not None


# ------------------- list & get -------------------

@router_v1.get("/services/list", operation_id="get_service_list")
async def get_service_list(x_api_key: str = Depends(validate_authbridge_api_key)):
    await reload_services()
    return {
        "detail": "List of services",
        "system_version": caches.service_sys_ver,
        "count": len(caches.services),
        "services": sorted(
            ({"name": s.name, "id": s.id, "type": s.type} for s in caches.services.values()),
            key=lambda x: (x["type"], x["name"]),
        ),
    }


@router_v1.get("/services", operation_id="get_services")
async def get_services(_: str = Depends(validate_authbridge_api_key)):
    await reload_services()
    return {
        "detail": "List of services",
        "system_version": caches.service_sys_ver,
        "count": len(caches.services),
        "services": list(caches.services.values()),
    }


@router_v1.get("/services/{service_id}", operation_id="get_service_by_id")
async def get_service_by_id(
    service_id: str = Path(...),
    api_key: str = Depends(get_header_api_key),
):
    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)
    return {"detail": "Service details", "system_version": caches.service_sys_ver, "service": service}


@router_v1.get("/services/{service_id}/version", operation_id="get_service_version")
async def get_service_version(
    service_id: str = Path(...),
    api_key: str = Depends(get_header_api_key),
):
    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)
    return {"detail": "Service details", "version": service.version}


# ------------------- create -------------------

@router_v1.post("/services", operation_id="create_service")
async def create_service(
    service: Optional[ServiceEntity] = Body(None),
    _: str = Depends(validate_authbridge_api_key),
):
    if service is None:
        raise HTTPException(status_code=400, detail={"error_code": "BAD_REQUEST", "message": "Service payload is required"})
    if await service_exists(service.id):
        raise HTTPException(status_code=400, detail={"error_code": "ALREADY_EXISTS", "message": "Service already exists"})

    rm = RedisManager()
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

    await rm.audit("service_created", "service", service.id, {"name": service.name, "type": service.type})

    return {
        "detail": "Service created",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "api_key": service.api_key,
    }


# ------------------- delete -------------------

@router_v1.delete("/services/{service_id}", operation_id="delete_service")
async def delete_service(
    service_id: str = Path(..., embed=True),
    x_api_key: str = Depends(validate_authbridge_api_key),
):
    # rate limit admin destructive ops
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 60, 60)

    service = await get_service(service_id)
    rm = RedisManager()

    # Optimistic concurrency: ensure no one updated service since we loaded it
    current = await rm.get_item(service_id, EntityType.SERVICE.value)
    if current and current.version != service.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Service modified concurrently"})

    # Remove links referencing this service across all workspaces
    await reload_workspaces()
    removed_links = []
    for workspace in list(caches.workspaces.values()):
        removed = []
        for link in list(workspace.services):
            if link.issuer_id == service_id or link.audience_id == service_id:
                workspace.services.remove(link)
                removed.append(link)
        if removed:
            new_ver_t = new_system_token()
            workspace.version = await rm.save_item(workspace, EntityType.WORKSPACE.value, new_ver_t)
            caches.workspaces[workspace.id] = workspace
            caches.workspace_sys_ver = new_ver_t
            removed_links.append(removed)

    new_ver = new_system_token()
    await rm.delete_item(service_id, EntityType.SERVICE.value, new_ver)
    caches.services.pop(service_id, None)
    caches.service_sys_ver = new_ver
    await rm.audit("service_deleted", "service", service_id, {"links_removed": len(removed_links)})

    return {
        "detail": "Service removed",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "links": removed_links,
    }


# ------------------- rekey -------------------

@router_v1.put("/services/{service_id}/rekey", operation_id="rekey_service")
async def rekey_service(
    service_id: str = Path(..., embed=True),
    x_api_key: str = Depends(validate_authbridge_api_key),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    # admin op rate limit
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 120, 60)

    service = await get_service(service_id)
    rm = RedisManager()

    # If-Match header support (optional)
    if if_match and if_match != service.version:
        raise HTTPException(status_code=412, detail={"error_code": "PRECONDITION_FAILED", "message": "If-Match does not match current version"})

    # Optimistic concurrency check
    current = await rm.get_item(service_id, EntityType.SERVICE.value)
    if current and current.version != service.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Service modified concurrently"})

    service.api_key = secrets.token_hex(32)
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

    await rm.audit("service_rekey", "service", service.id, {})

    return {
        "detail": "Service API_KEY regenerated",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "api_key": service.api_key,
    }


# ------------------- update content/info -------------------

@router_v1.put("/services/{service_id}/content", operation_id="update_service_content")
async def update_service_content(
    service_id: str = Path(..., embed=True),
    content: dict = Body(..., description="The updated content for the service"),
    x_api_key: str = Depends(validate_authbridge_api_key),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 240, 60)

    service = await get_service(service_id)
    rm = RedisManager()

    if if_match and if_match != service.version:
        raise HTTPException(status_code=412, detail={"error_code": "PRECONDITION_FAILED", "message": "If-Match does not match current version"})

    # Optimistic concurrency check
    current = await rm.get_item(service_id, EntityType.SERVICE.value)
    if current and current.version != service.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Service modified concurrently"})

    service.content = content
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

    await rm.audit("service_content_updated", "service", service.id, {"keys": list(content.keys())})

    return {
        "detail": "Service content updated",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "content": service.content,
    }


@router_v1.put("/services/{service_id}/info", operation_id="update_service_info")
async def update_service_info(
    service_id: str = Path(..., embed=True),
    info: dict = Body(..., description="The updated info for the service"),
    x_api_key: str = Depends(validate_authbridge_api_key),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 240, 60)

    service = await get_service(service_id)
    rm = RedisManager()

    if if_match and if_match != service.version:
        raise HTTPException(status_code=412, detail={"error_code": "PRECONDITION_FAILED", "message": "If-Match does not match current version"})

    current = await rm.get_item(service_id, EntityType.SERVICE.value)
    if current and current.version != service.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Service modified concurrently"})

    service.info = info
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

    await rm.audit("service_info_updated", "service", service.id, {"keys": list(info.keys())})

    return {
        "detail": "Service info updated",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "info": service.info,
    }


@router_v1.get(
    "/services/{service_id}/discovery",
    operation_id="service_discovery",
    response_model=DiscoveryResponse,
)
async def service_discovery_v1(
    service_id: str = Path(...),
    api_key: str = Depends(get_header_api_key),
) -> DiscoveryResponse:
    s = get_settings()
    await check_rate_limit("discovery", api_key, s.RL_DISCOVERY_LIMIT_PER_MIN, 60)

    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)
    await reload_workspaces()

    found_links = [
        DiscoveredServiceLink(workspace_id=t.id, service_id=link.audience_id, context=link.context)
        for t in caches.workspaces.values()
        for link in t.services
        if link.issuer_id == service.id
    ]

    links_map: Dict[str, List[str]] = {}
    contexts_map: Dict[str, List[dict]] = {}
    for link in found_links:
        links_map.setdefault(link.service_id, []).append(link.workspace_id)
        if link.context:
            contexts_map.setdefault(link.service_id, []).append(link.context)

    discovered_services: List[Union[DiscoveredService, dict]] = []
    for s_id, workspace_list in links_map.items():
        discovered_service = await get_service(s_id)
        discovered_workspaces: List[WorkspaceLimited] = []
        for w_id in workspace_list:
            workspace = await get_workspace(w_id)
            discovered_workspaces.append(
                WorkspaceLimited(
                    name=workspace.name,
                    id=workspace.id,
                    version=workspace.version,
                    info=workspace.info,
                )
            )
        ds = DiscoveredService(
            service=ServiceLimited(
                name=discovered_service.name,
                id=discovered_service.id,
                type=discovered_service.type,
                version=discovered_service.version,
                info=discovered_service.info,
            ),
            workspaces=discovered_workspaces,
        )
        ds_dict = ds.model_dump()
        if s_id in contexts_map:
            ds_dict["contexts"] = contexts_map[s_id]
            discovered_services.append(ds_dict)
        else:
            discovered_services.append(ds)

    rm = RedisManager()
    await rm.audit("discovery", "service", service.id, {"links": len(discovered_services)})

    return DiscoveryResponse(
        detail="Service link(s) discovered",
        system_version=caches.service_sys_ver,
        service=service,
        links=discovered_services,
    )


# ------------------- who can call me (incoming) -------------------

@router_v1.get("/services/{service_id}/callers", operation_id="get_service_callers")
async def get_service_callers(
    service_id: str = Path(..., embed=True),
    api_key: str = Depends(get_header_api_key),
):
    s = get_settings()
    await check_rate_limit("discovery", api_key, s.RL_DISCOVERY_LIMIT_PER_MIN, 60)

    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)

    await reload_workspaces()
    callers = []
    for workspace in caches.workspaces.values():
        for link in workspace.services:
            if link.audience_id == service_id:
                callers.append({
                    "workspace_id": workspace.id,
                    "issuer_service_id": link.issuer_id,
                    "context": link.context,
                })

    rm = RedisManager()
    await rm.audit("who_can_call_me", "service", service_id, {"callers": len(callers)})

    return {
        "detail": "Allowed callers",
        "service_id": service_id,
        "count": len(callers),
        "callers": callers,
    }
