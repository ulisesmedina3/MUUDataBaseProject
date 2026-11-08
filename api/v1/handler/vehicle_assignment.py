from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.vehicle_assignment import (
    AssignmentNotFoundError,
    AssignmentReferenceNotFoundError,
    create_assignment,
    delete_assignment,
    get_assignment,
    get_assignments,
    update_assignment,
)


class AssignmentCreate(BaseModel):
    vehicle_id: int = Field(gt=0)
    driver_id: int = Field(gt=0)
    assigned_from: datetime
    assigned_to: datetime | None = None


class AssignmentUpdate(BaseModel):
    vehicle_id: int | None = Field(default=None, gt=0)
    driver_id: int | None = Field(default=None, gt=0)
    assigned_from: datetime | None = None
    assigned_to: datetime | None = None


router = APIRouter(prefix="/api/v1/vehicle-assignments", tags=["vehicle-assignments"])


def _connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return pool, pool.getconn()


def _integer(value: str, name: str, positive: bool = False) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        requirement = "positive" if positive else "non-negative"
        raise HTTPException(status_code=400, detail=f"{name} must be a {requirement} integer") from exc
    if (positive and parsed <= 0) or (not positive and parsed < 0):
        requirement = "positive" if positive else "non-negative"
        raise HTTPException(status_code=400, detail=f"{name} must be a {requirement} integer")
    return parsed


def _ordered(assigned_from: datetime, assigned_to: datetime | None) -> None:
    if assigned_to is None:
        return
    start = assigned_from if assigned_from.tzinfo else assigned_from.replace(tzinfo=timezone.utc)
    end = assigned_to if assigned_to.tzinfo else assigned_to.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(status_code=422, detail="The assignment time interval is invalid")


@router.post("", status_code=201)
async def create_assignment_route(request: Request):
    try:
        payload = AssignmentCreate.model_validate(await request.json())
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON or invalid payload shape") from exc
    _ordered(payload.assigned_from, payload.assigned_to)
    pool, connection = _connection(request)
    try:
        try:
            return create_assignment(connection, **payload.model_dump())
        except AssignmentReferenceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Referenced vehicle_id or driver_id does not exist") from exc
    finally:
        pool.putconn(connection)


@router.get("")
def list_assignments_route(request: Request, limit: str = "20", offset: str = "0",
                           vehicle_id: str | None = None, driver_id: str | None = None,
                           active: str | None = None):
    limit_value = _integer(limit, "limit")
    offset_value = _integer(offset, "offset")
    vehicle_value = _integer(vehicle_id, "vehicle_id", True) if vehicle_id is not None else None
    driver_value = _integer(driver_id, "driver_id", True) if driver_id is not None else None
    active_value = None
    if active is not None:
        if active.lower() not in ("true", "false"):
            raise HTTPException(status_code=400, detail="active must be true or false")
        active_value = active.lower() == "true"
    pool, connection = _connection(request)
    try:
        items, count = get_assignments(connection, limit_value, offset_value, vehicle_value, driver_value, active_value)
    finally:
        pool.putconn(connection)
    return {"items": items, "limit": limit_value, "offset": offset_value, "count": count}


@router.get("/{assignment_id}")
def get_assignment_route(request: Request, assignment_id: str):
    assignment_value = _integer(assignment_id, "assignment_id", True)
    pool, connection = _connection(request)
    try:
        try:
            return get_assignment(connection, assignment_value)
        except AssignmentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="assignment_id does not exist") from exc
    finally:
        pool.putconn(connection)


@router.put("/{assignment_id}")
async def update_assignment_route(request: Request, assignment_id: str):
    assignment_value = _integer(assignment_id, "assignment_id", True)
    try:
        payload = AssignmentUpdate.model_validate(await request.json())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="The assignment time interval is invalid") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON or empty update payload") from exc
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Malformed JSON or empty update payload")
    if any(data.get(field) is None for field in ("vehicle_id", "driver_id", "assigned_from") if field in data):
        raise HTTPException(status_code=422, detail="The assignment time interval is invalid")
    pool, connection = _connection(request)
    try:
        try:
            current = get_assignment(connection, assignment_value)
            assigned_from = data.get("assigned_from", datetime.fromisoformat(current["assigned_from"].replace("Z", "+00:00")))
            assigned_to = data.get("assigned_to", datetime.fromisoformat(current["assigned_to"].replace("Z", "+00:00")) if current["assigned_to"] else None)
            _ordered(assigned_from, assigned_to)
            return update_assignment(connection, assignment_value, data)
        except AssignmentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="assignment_id does not exist") from exc
        except AssignmentReferenceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Referenced vehicle_id or driver_id does not exist") from exc
    finally:
        pool.putconn(connection)


@router.delete("/{assignment_id}")
def delete_assignment_route(request: Request, assignment_id: str):
    assignment_value = _integer(assignment_id, "assignment_id", True)
    pool, connection = _connection(request)
    try:
        try:
            return delete_assignment(connection, assignment_value)
        except AssignmentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="assignment_id does not exist") from exc
    finally:
        pool.putconn(connection)
