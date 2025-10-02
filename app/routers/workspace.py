from __future__ import annotations

import secrets
from typing import Optional

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
from app.models import EntityType, WorkspaceEntity, ServiceLink
from app.settings import get_settings

log = get_logger("auth-bridge.workspace")

router = APIRouter(prefix="/api/v1", tags=["workspaces"])


async def reload_workspaces(with_log: bool = False) -> None:
    rm = RedisManager()
    await caches.reload_workspaces_if_needed(rm, log_details=with_log)


async def get_workspace(workspace_id: str) -> WorkspaceEntity:
    await reload_workspaces()
    workspace = caches.workspaces.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": "Workspace not found after [get_workspace]"})
    return workspace


async def workspace_exists(workspace_id: str) -> bool:
    rm = RedisManager()
    return (await rm.get_item(workspace_id, EntityType.WORKSPACE.value)) is not None


# ------------------- list & get -------------------

@router.get("/workspaces/list", operation_id="get_workspace_list")
async def get_workspace_list(x_api_key: str = Depends(validate_authbridge_api_key)):
    await reload_workspaces()
    return {
        "detail": "List of workspaces",
        "system_version": caches.workspace_sys_ver,
        "count": len(caches.workspaces),
        "workspaces": [{"name": t.name, "id": t.id} for t in sorted(caches.workspaces.values(), key=lambda x: x.name)],
    }


@router.get("/workspaces", operation_id="get_workspaces")
async def get_workspaces(_: str = Depends(validate_authbridge_api_key)):
    await reload_workspaces()
    return {
        "detail": "List of workspaces",
        "system_version": caches.workspace_sys_ver,
        "count": len(caches.workspaces),
        "workspaces": [t.to_dict() for t in caches.workspaces.values()],
    }


@router.get("/workspaces/{workspace_id}", operation_id="get_workspace_by_id")
async def get_workspace_by_id(
    workspace_id: str = Path(...),
    api_key: str = Depends(get_header_api_key),
):
    workspace = await get_workspace(workspace_id)
    await validate_item_api_key(api_key, workspace, EntityType.WORKSPACE)
    return {"detail": "Workspace details", "system_version": caches.workspace_sys_ver, "workspace": workspace.to_dict()}


@router.get("/workspaces/{workspace_id}/version", operation_id="get_workspace_version")
async def get_workspace_version(
    workspace_id: str = Path(...),
    api_key: str = Depends(get_header_api_key),
):
    workspace = await get_workspace(workspace_id)
    await validate_item_api_key(api_key, workspace, EntityType.WORKSPACE)
    return {"detail": "Workspace details", "version": workspace.version}


# ------------------- create -------------------

@router.post("/workspaces", operation_id="create_workspace")
async def create_workspace(
    workspace: WorkspaceEntity = Body(...),
    x_api_key: str = Depends(validate_authbridge_api_key),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 120, 60)

    if await workspace_exists(workspace.id):
        raise HTTPException(status_code=400, detail={"error_code": "ALREADY_EXISTS", "message": "Workspace already exists"})

    rm = RedisManager()
    new_ver = new_system_token()
    workspace.version = await rm.save_item(workspace, EntityType.WORKSPACE.value, new_ver)

    caches.workspaces[workspace.id] = workspace
    caches.workspace_sys_ver = new_ver

    await rm.audit("workspace_created", "workspace", workspace.id, {"name": workspace.name})

    return {
        "detail": "Workspace created",
        "system_version": caches.workspace_sys_ver,
        "version": workspace.version,
        "name": workspace.name,
        "id": workspace.id,
        "api_key": workspace.api_key,
        "services": workspace.services,
    }


# ------------------- delete -------------------

@router.delete("/workspaces/{workspace_id}", operation_id="delete_workspace")
async def delete_workspace(
    workspace_id: str = Path(..., embed=True),
    x_api_key: str = Depends(validate_authbridge_api_key),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 60, 60)

    workspace = await get_workspace(workspace_id)
    rm = RedisManager()

    # optimistic concurrency check
    current = await rm.get_item(workspace_id, EntityType.WORKSPACE.value)
    if current and current.version != workspace.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Workspace modified concurrently"})

    new_ver = new_system_token()
    await rm.delete_item(workspace_id, EntityType.WORKSPACE.value, new_ver)

    caches.workspaces.pop(workspace_id, None)
    caches.workspace_sys_ver = new_ver

    await rm.audit("workspace_deleted", "workspace", workspace_id, {})

    return {
        "detail": "Workspace removed",
        "system_version": caches.workspace_sys_ver,
        "version": workspace.version,
        "id": workspace.id,
    }


# ------------------- rekey -------------------

@router.put("/workspaces/{workspace_id}/rekey", operation_id="rekey_workspace")
async def rekey_workspace(
    workspace_id: str = Path(..., embed=True),
    x_api_key: str = Depends(validate_authbridge_api_key),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 120, 60)

    workspace = await get_workspace(workspace_id)
    rm = RedisManager()

    if if_match and if_match != workspace.version:
        raise HTTPException(status_code=412, detail={"error_code": "PRECONDITION_FAILED", "message": "If-Match does not match current version"})

    # concurrency check
    current = await rm.get_item(workspace_id, EntityType.WORKSPACE.value)
    if current and current.version != workspace.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Workspace modified concurrently"})

    workspace.api_key = secrets.token_hex(32)
    new_ver = new_system_token()
    workspace.version = await rm.save_item(workspace, EntityType.WORKSPACE.value, new_ver)

    caches.workspaces[workspace.id] = workspace
    caches.workspace_sys_ver = new_ver

    await rm.audit("workspace_rekey", "workspace", workspace.id, {})

    return {
        "detail": "Workspace API_KEY regenerated",
        "system_version": caches.workspace_sys_ver,
        "version": workspace.version,
        "name": workspace.name,
        "id": workspace.id,
        "api_key": workspace.api_key,
    }


# ------------------- link / unlink service -------------------

@router.post("/workspaces/{workspace_id}/{action}", operation_id="link_service")
async def link_service(
    workspace_id: str = Path(...),
    action: str = Path(...),
    service_link: ServiceLink = Body(...),
    x_api_key: str = Depends(validate_authbridge_api_key),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 240, 60)

    from app.routers.service import reload_services  # avoid cycle
    workspace = await get_workspace(workspace_id)
    await reload_services()

    if service_link.issuer_id == service_link.audience_id:
        raise HTTPException(status_code=404, detail={"error_code": "BAD_LINK", "message": "Service cannot be linked to itself"})

    if service_link.issuer_id not in caches.services:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": f"Service [{service_link.issuer_id}] not found"})
    if service_link.audience_id not in caches.services:
        raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND", "message": f"Service [{service_link.audience_id}] not found"})

    # concurrency check
    rm = RedisManager()
    if if_match and if_match != workspace.version:
        raise HTTPException(status_code=412, detail={"error_code": "PRECONDITION_FAILED", "message": "If-Match does not match current version"})
    current = await rm.get_item(workspace_id, EntityType.WORKSPACE.value)
    if current and current.version != workspace.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Workspace modified concurrently"})

    if action == "link-service":
        if service_link in workspace.services:
            raise HTTPException(status_code=404, detail={"error_code": "ALREADY_LINKED", "message": "Service already linked"})
        workspace.services.append(service_link)
    elif action == "unlink-service":
        if service_link not in workspace.services:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_LINKED", "message": "Service is not linked"})
        workspace.services.remove(service_link)
    else:
        raise HTTPException(status_code=404, detail={"error_code": "BAD_ACTION", "message": f"Incorrect action:{action} provided"})

    new_ver = new_system_token()
    workspace.version = await rm.save_item(workspace, EntityType.WORKSPACE.value, new_ver)

    caches.workspaces[workspace.id] = workspace
    caches.workspace_sys_ver = new_ver

    await rm.audit("workspace_link_change", "workspace", workspace.id, {"action": action})

    return {
        "detail": f"Successful action: {action}",
        "system_version": caches.workspace_sys_ver,
        "version": workspace.version,
        "workspace_id": workspace.id,
        "link": service_link,
    }


# ------------------- update content / info -------------------

@router.put("/workspaces/{workspace_id}/content", operation_id="update_workspace_content")
async def update_workspace_content(
    workspace_id: str = Path(..., embed=True),
    content: dict = Body(..., description="The updated content for the workspace"),
    x_api_key: str = Depends(validate_authbridge_api_key),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 240, 60)

    workspace = await get_workspace(workspace_id)

    rm = RedisManager()
    if if_match and if_match != workspace.version:
        raise HTTPException(status_code=412, detail={"error_code": "PRECONDITION_FAILED", "message": "If-Match does not match current version"})
    current = await rm.get_item(workspace_id, EntityType.WORKSPACE.value)
    if current and current.version != workspace.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Workspace modified concurrently"})

    workspace.content = content
    new_ver = new_system_token()
    workspace.version = await rm.save_item(workspace, EntityType.WORKSPACE.value, new_ver)

    caches.workspaces[workspace.id] = workspace
    caches.workspace_sys_ver = new_ver

    await rm.audit("workspace_content_updated", "workspace", workspace.id, {"keys": list(content.keys())})

    return {
        "detail": "Workspace content updated",
        "system_version": caches.workspace_sys_ver,
        "version": workspace.version,
        "name": workspace.name,
        "id": workspace.id,
        "content": workspace.content,
    }


@router.put("/workspaces/{workspace_id}/info", operation_id="update_workspace_info")
async def update_workspace_info(
    workspace_id: str = Path(..., embed=True),
    info: dict = Body(..., description="The updated info for the workspace"),
    x_api_key: str = Depends(validate_authbridge_api_key),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 240, 60)

    workspace = await get_workspace(workspace_id)

    rm = RedisManager()
    if if_match and if_match != workspace.version:
        raise HTTPException(status_code=412, detail={"error_code": "PRECONDITION_FAILED", "message": "If-Match does not match current version"})
    current = await rm.get_item(workspace_id, EntityType.WORKSPACE.value)
    if current and current.version != workspace.version:
        raise HTTPException(status_code=409, detail={"error_code": "CONFLICT", "message": "Workspace modified concurrently"})

    workspace.info = info
    new_ver = new_system_token()
    workspace.version = await rm.save_item(workspace, EntityType.WORKSPACE.value, new_ver)

    caches.workspaces[workspace.id] = workspace
    caches.workspace_sys_ver = new_ver

    await rm.audit("workspace_info_updated", "workspace", workspace.id, {"keys": list(info.keys())})

    return {
        "detail": "Workspace info updated",
        "system_version": caches.workspace_sys_ver,
        "version": workspace.version,
        "name": workspace.name,
        "id": workspace.id,
        "info": workspace.info,
    }
