from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.vehicle import (
    DuplicatePlateError,
    VehicleReferenceNotFoundError,
    VehicleDeleteConflictError,
    VehicleNotFoundError,
    create_vehicle,
    delete_vehicle,
    get_current_location,
    get_vehicle,
    get_vehicles,
    update_vehicle,
)


class VehicleCreate(BaseModel):
    vehicle_type_id: int
    vehicle_status_id: int
    plate_number: str = Field(min_length=1)
    make: str | None = None
    model: str | None = None
    year: int = Field(ge=1950, le=2100)


class VehicleUpdate(BaseModel):
    vehicle_type_id: int | None = None
    vehicle_status_id: int | None = None
    plate_number: str | None = Field(default=None, min_length=1)
    make: str | None = None
    model: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)


router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


def _get_connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return pool, pool.getconn()


def _parse_id(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="vehicle_id must be a positive integer",
        ) from exc
    if parsed <= 0:
        raise HTTPException(status_code=400, detail="vehicle_id must be a positive integer")
    return parsed


@router.get("")
def get_vehicles_route(
    request: Request,
    limit: str = "20",
    offset: str = "0",
    status: str | None = None,
    plate_number: str | None = None,
):
    try:
        parsed_limit = int(limit)
        parsed_offset = int(offset)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="limit and offset must be non-negative integers",
        ) from exc
    if parsed_limit < 0 or parsed_offset < 0:
        raise HTTPException(
            status_code=400,
            detail="limit and offset must be non-negative integers",
        )
    pool, connection = _get_connection(request)
    try:
        items, count = get_vehicles(
            connection,
            parsed_limit,
            parsed_offset,
            status,
            plate_number,
        )
    finally:
        pool.putconn(connection)

    return {
        "items": items,
        "limit": parsed_limit,
        "offset": parsed_offset,
        "count": count,
    }


@router.post("", status_code=201)
async def create_vehicle_route(request: Request):
    try:
        payload = VehicleCreate.model_validate(await request.json())
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON or invalid payload") from exc

    pool, connection = _get_connection(request)
    try:
        plate_number = payload.plate_number.strip()
        if not plate_number:
            raise HTTPException(status_code=400, detail="plate_number must not be empty")
        try:
            vehicle = create_vehicle(
                connection,
                payload.vehicle_type_id,
                payload.vehicle_status_id,
                plate_number,
                payload.make.strip() if payload.make is not None else None,
                payload.model.strip() if payload.model is not None else None,
                payload.year,
            )
        except VehicleReferenceNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="vehicle_type_id or vehicle_status_id does not exist",
            ) from exc
        except DuplicatePlateError as exc:
            raise HTTPException(
                status_code=409,
                detail="plate_number already exists",
            ) from exc
    finally:
        pool.putconn(connection)

    return vehicle


@router.get("/{vehicle_id}")
def get_vehicle_route(request: Request, vehicle_id: str):
    vehicle_id = _parse_id(vehicle_id)
    pool, connection = _get_connection(request)
    try:
        try:
            return get_vehicle(connection, vehicle_id)
        except VehicleNotFoundError as exc:
            raise HTTPException(status_code=404, detail="vehicle_id does not exist") from exc
    finally:
        pool.putconn(connection)


@router.put("/{vehicle_id}")
async def update_vehicle_route(request: Request, vehicle_id: str):
    vehicle_id = _parse_id(vehicle_id)
    try:
        payload = VehicleUpdate.model_validate(await request.json())
        data = payload.model_dump(exclude_unset=True)
        for field in ("plate_number", "make", "model"):
            if field in data and data[field] is not None:
                data[field] = data[field].strip()
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON or empty payload") from exc
    if not data:
        raise HTTPException(status_code=400, detail="Malformed JSON or empty payload")
    if any(value is None for value in data.values()):
        raise HTTPException(status_code=400, detail="Malformed JSON or empty payload")

    pool, connection = _get_connection(request)
    try:
        try:
            return update_vehicle(connection, vehicle_id, data)
        except VehicleNotFoundError as exc:
            raise HTTPException(status_code=404, detail="vehicle_id does not exist") from exc
        except VehicleReferenceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Referenced foreign key does not exist") from exc
        except DuplicatePlateError as exc:
            raise HTTPException(status_code=409, detail="plate_number already exists") from exc
    finally:
        pool.putconn(connection)


@router.delete("/{vehicle_id}")
def delete_vehicle_route(request: Request, vehicle_id: str):
    vehicle_id = _parse_id(vehicle_id)
    pool, connection = _get_connection(request)
    try:
        try:
            return delete_vehicle(connection, vehicle_id)
        except VehicleNotFoundError as exc:
            raise HTTPException(status_code=404, detail="vehicle_id does not exist") from exc
        except VehicleDeleteConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail="Vehicle is referenced and cannot be deleted",
            ) from exc
    finally:
        pool.putconn(connection)


@router.get("/{vehicle_id}/current-location", status_code=200)
def current_location_route(request: Request, vehicle_id: str):
    vehicle_id = _parse_id(vehicle_id)
    pool, connection = _get_connection(request)
    try:
        try:
            location = get_current_location(connection, vehicle_id)
        except VehicleNotFoundError as exc:
            raise HTTPException(status_code=404, detail="vehicle_id does not exist") from exc
    finally:
        pool.putconn(connection)
    if location is None:
        return Response(status_code=204)
    return location
