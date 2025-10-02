from __future__ import annotations

import secrets
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path

from app.core.logging import get_logger
from app.core.redis import RedisManager, caches
from app.core.security import (
    get_header_api_key,
    validate_authbridge_api_key,
    validate_item_api_key,
    new_system_token,
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
        raise HTTPException(status_code=404, detail="Service not found after [get_service]")
    return service


async def service_exists(service_id: str) -> bool:
    rm = RedisManager()
    return (await rm.get_item(service_id, EntityType.SERVICE.value)) is not None


@router_v1.get("/services/list", operation_id="get_service_list")
async def get_service_list(_: str = Depends(validate_authbridge_api_key)):
    await reload_services()
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for s in caches.services.values():
        grouped[s.type].append({"name": s.name, "id": s.id})
    sorted_grouped = {k: sorted(v, key=lambda s: s["name"]) for k, v in grouped.items()}
    return {
        "detail": "List of services",
        "system_version": caches.service_sys_ver,
        "count": len(caches.services),
        "services": sorted_grouped,
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


@router_v1.post("/services", operation_id="create_service")
async def create_service(
    service: Optional[ServiceEntity] = Body(None),
    _: str = Depends(validate_authbridge_api_key),
):
    if service is None:
        raise HTTPException(status_code=400, detail="Service payload is required")
    if await service_exists(service.id):
        raise HTTPException(status_code=400, detail="Error. Service already exists!")

    rm = RedisManager()
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

    return {
        "detail": "Service created",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "api_key": service.api_key,
    }


@router_v1.get("/services/{service_id}/link/{workspace_id}", operation_id="get_service_link_by_workspace")
async def get_service_link_by_workspace(
    service_id: str = Path(..., embed=True),
    workspace_id: str = Path(..., embed=True),
    api_key: str = Depends(get_header_api_key),
):
    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)
    workspace = await get_workspace(workspace_id)

    links = [link for link in workspace.services if link.issuer_id == service_id or link.audience_id == service_id]
    return {"detail": "Service-Workspace Link", "name": service.name, "id": service.id, "type": service.type, "links": links}


@router_v1.get("/services/{service_id}/links", operation_id="get_service_links")
async def get_service_links(
    service_id: str = Path(..., embed=True),
    api_key: str = Depends(get_header_api_key),
):
    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)

    await reload_workspaces()
    links = []
    for workspace in caches.workspaces.values():
        for link in workspace.services:
            if link.issuer_id == service_id or link.audience_id == service_id:
                links.append({"workspace_id": workspace.id, "link": link})
    return {"detail": "Service Links", "name": service.name, "id": service.id, "type": service.type, "links": links}


@router_v1.delete("/services/{service_id}", operation_id="delete_service")
async def delete_service(
    service_id: str = Path(..., embed=True),
    _: str = Depends(validate_authbridge_api_key),
):
    service = await get_service(service_id)

    await reload_workspaces()
    rm = RedisManager()
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

    return {
        "detail": "Service removed",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "links": removed_links,
    }


@router_v1.put("/services/{service_id}/rekey", operation_id="rekey_service")
async def rekey_service(
    service_id: str = Path(..., embed=True),
    _: str = Depends(validate_authbridge_api_key),
):
    service = await get_service(service_id)
    rm = RedisManager()
    service.api_key = secrets.token_hex(32)
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

    return {
        "detail": "Service API_KEY regenerated",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "api_key": service.api_key,
    }


@router_v1.put("/services/{service_id}/content", operation_id="update_service_content")
async def update_service_content(
    service_id: str = Path(..., embed=True),
    content: dict = Body(..., description="The updated content for the service"),
    _: str = Depends(validate_authbridge_api_key),
):
    service = await get_service(service_id)
    rm = RedisManager()
    service.content = content
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

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
    _: str = Depends(validate_authbridge_api_key),
):
    service = await get_service(service_id)
    rm = RedisManager()
    service.info = info
    new_ver = new_system_token()
    service.version = await rm.save_item(service, EntityType.SERVICE.value, new_ver)

    caches.services[service.id] = service
    caches.service_sys_ver = new_ver

    return {
        "detail": "Service info updated",
        "system_version": caches.service_sys_ver,
        "version": service.version,
        "name": service.name,
        "id": service.id,
        "type": service.type,
        "info": service.info,
    }


@router_v1.get("/services/{service_id}/discovery", operation_id="service_discovery_v1")
async def service_discovery_v1(
    service_id: str = Path(...),
    api_key: str = Depends(get_header_api_key),
):
    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)
    await reload_workspaces()

    found_links = [
        DiscoveredServiceLink(workspace_id=t.id, service_id=link.audience_id, context=link.context)
        for t in caches.workspaces.values()
        for link in t.services
        if link.issuer_id == service.id
    ]

    links = []
    jwts = []
    for link in found_links:
        link_service = await get_service(link.service_id)
        link_workspace = caches.workspaces.get(link.workspace_id)
        links.append(
            {
                "service": {"name": link_service.name, "id": link_service.id, "info": link_service.info},
                "workspace": {"name": link_workspace.name, "id": link_workspace.id, "info": link_workspace.info},
                "context": link.context,
            }
        )

        for server in link_workspace.services:
            ctx = server.context or {}
            jwts.append(
                {
                    "jwt": {
                        "iss": server.issuer_id,
                        "aud": server.audience_id,
                        "sub": link_workspace.id,
                        "database": ctx.get("database"),
                        "schema": ctx.get("schema"),
                    }
                }
            )

    return {
        "detail": "Service link(s) discovered",
        "system_version": caches.service_sys_ver,
        "service": {
            "name": service.name,
            "id": service.id,
            "api_key": service.api_key,
            "version": service.version,
            "content": service.content,
            "info": service.info,
        },
        "links": links,
        "token_payloads": jwts,
    }


@router_v2.get("/services/{service_id}/discovery", operation_id="service_discovery_v2", response_model=DiscoveryResponse)
async def service_discovery_v2(
    service_id: str = Path(...),
    api_key: str = Depends(get_header_api_key),
) -> DiscoveryResponse:
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
    for link in found_links:
        links_map.setdefault(link.service_id, []).append(link.workspace_id)

    discovered_services: List[DiscoveredService] = []
    for s_id, workspace_list in links_map.items():
        discovered_service = await get_service(s_id)
        discovered_workspaces: List[WorkspaceLimited] = []
        for w_id in workspace_list:
            workspace = await get_workspace(w_id)
            discovered_workspaces.append(
                WorkspaceLimited(name=workspace.name, id=workspace.id, version=workspace.version, info=workspace.info)
            )
        discovered_services.append(
            DiscoveredService(
                service=ServiceLimited(
                    name=discovered_service.name,
                    id=discovered_service.id,
                    type=discovered_service.type,
                    version=discovered_service.version,
                    info=discovered_service.info,
                ),
                workspaces=discovered_workspaces,
            )
        )

    return DiscoveryResponse(
        detail="Service link(s) discovered",
        system_version=caches.service_sys_ver,
        service=service,
        links=discovered_services,
    )
