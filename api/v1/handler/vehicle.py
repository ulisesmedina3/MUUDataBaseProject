from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.vehicle import (
    DuplicatePlateError,
    VehicleReferenceNotFoundError,
    create_vehicle,
    get_vehicles,
)


class VehicleCreate(BaseModel):
    vehicle_type_id: int
    vehicle_status_id: int
    plate_number: str = Field(min_length=1)
    make: str | None = None
    model: str | None = None
    year: int = Field(ge=1950, le=2100)


router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


def _get_connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return pool, pool.getconn()


@router.get("")
def get_vehicles_route(
    request: Request,
    limit: Annotated[int, Query(ge=0)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: str | None = None,
    plate_number: str | None = None,
):
    pool, connection = _get_connection(request)
    try:
        items, count = get_vehicles(
            connection,
            limit,
            offset,
            status,
            plate_number,
        )
    finally:
        pool.putconn(connection)

    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "count": count,
    }


@router.post("", status_code=201)
def create_vehicle_route(payload: VehicleCreate, request: Request):
    pool, connection = _get_connection(request)
    try:
        try:
            vehicle = create_vehicle(
                connection,
                payload.vehicle_type_id,
                payload.vehicle_status_id,
                payload.plate_number.strip(),
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
