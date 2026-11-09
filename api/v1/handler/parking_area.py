from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.parking_area import (
    InvalidParkingAreaGeometryError,
    ParkingArea,
    ParkingAreaCreate,
    ParkingAreaDAO,
    ParkingAreaNotFoundError,
    ParkingAreaUpdate,
)


router = APIRouter(prefix="/api/v1/parking-areas", tags=["parking-areas"])


def _connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return pool, pool.getconn()


def _parse_bbox(bbox: str | None) -> list[float] | None:
    if bbox is None:
        return None
    try:
        values = [float(value) for value in bbox.split(",")]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid bounding box coordinates.") from exc

    if (
        len(values) != 4
        or not all(math.isfinite(value) for value in values)
        or values[0] >= values[2]
        or values[1] >= values[3]
        or not (-180 <= values[0] <= 180 and -180 <= values[2] <= 180)
        or not (-90 <= values[1] <= 90 and -90 <= values[3] <= 90)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid bounding box coordinates. Ensure that min_Longitude < "
                "max_Longitude and min_Latitude < max_Latitude."
            ),
        )
    return values


@router.post("", status_code=201)
def create_parking_area(payload: ParkingAreaCreate, request: Request) -> ParkingArea:
    pool, connection = _connection(request)
    try:
        try:
            return ParkingAreaDAO.create_parking_area(connection, payload)
        except InvalidParkingAreaGeometryError as exc:
            raise HTTPException(
                status_code=400,
                detail="Malformed geometry or invalid JSON",
            ) from exc
    finally:
        pool.putconn(connection)


@router.get("")
def get_parking_areas(
    request: Request,
    name: str | None = None,
    bbox: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    if limit < 0:
        raise HTTPException(status_code=400, detail="Limit cannot be negative.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset cannot be negative.")

    pool, connection = _connection(request)
    try:
        return ParkingAreaDAO.get_parking_areas(
            connection,
            name,
            _parse_bbox(bbox),
            limit,
            offset,
        )
    finally:
        pool.putconn(connection)


@router.get("/{parking_area_id}")
def get_parking_area(request: Request, parking_area_id: int):
    if parking_area_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid parking_area_id. Must be a positive integer.",
        )

    pool, connection = _connection(request)
    try:
        parking_area = ParkingAreaDAO.get_parking_area_by_id(
            connection, parking_area_id
        )
    finally:
        pool.putconn(connection)

    if parking_area is None:
        raise HTTPException(
            status_code=404,
            detail=f"Parking area with ID {parking_area_id} not found.",
        )
    return parking_area

@router.put("/{parking_area_id}")
def update_parking_area(
    parking_area_id: int,
    payload: ParkingAreaUpdate,
    request: Request,
):
    if parking_area_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="parking_area_id must be a positive integer",
        )

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update.",
        )

    pool, connection = _connection(request)
    try:
        try:
            return ParkingAreaDAO.update_parking_area(
                connection, parking_area_id, updates
            )
        except ParkingAreaNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Parking area with ID {parking_area_id} not found.",
            ) from exc
        except InvalidParkingAreaGeometryError as exc:
            raise HTTPException(
                status_code=400,
                detail="geom must be a valid GeoJSON Polygon.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        pool.putconn(connection)

@router.delete("/{parking_area_id}")
def delete_parking_area(request: Request, parking_area_id: int):
    if parking_area_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid parking_area_id. Must be a positive integer.",
        )

    pool, connection = _connection(request)
    try:
        deleted = ParkingAreaDAO.delete_parking_area_by_id(
            connection, parking_area_id
        )
    finally:
        pool.putconn(connection)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Parking area with ID {parking_area_id} not found.",
        )
    return {
        "message": "Parking area deleted successfully",
        "parking_area_id": parking_area_id,
    }