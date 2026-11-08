from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.trip import (
    InvalidTripGeometryError, TripNotFoundError, TripVehicleNotFoundError,
    create_trip, delete_trip, get_trip, get_trips, update_trip, validate_point,
)


class TripCreate(BaseModel):
    vehicle_id: int = Field(gt=0)
    start_ts: datetime
    end_ts: datetime
    start_geom: dict[str, Any] | None = None
    end_geom: dict[str, Any] | None = None
    distance_km: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class TripUpdate(BaseModel):
    vehicle_id: int | None = Field(default=None, gt=0)
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    start_geom: dict[str, Any] | None = None
    end_geom: dict[str, Any] | None = None
    distance_km: float | None = Field(default=None, ge=0, allow_inf_nan=False)


router = APIRouter(prefix="/api/v1/trips", tags=["trips"])
vehicle_trips_router = APIRouter(prefix="/api/v1/vehicles", tags=["trips"])


def _connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(503, "Database connection unavailable")
    return pool, pool.getconn()


def _integer(value: str, name: str, positive: bool = False) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise HTTPException(400, f"{name} must be an integer") from exc
    if (positive and result <= 0) or (not positive and result < 0):
        requirement = "positive" if positive else "non-negative"
        raise HTTPException(400, f"{name} must be a {requirement} integer")
    return result


def _time(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, f"Invalid {name}") from exc


def _ordered(start: datetime, end: datetime) -> None:
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(400, "end_ts must be later than start_ts")


def _geometry(value: dict[str, Any] | None) -> None:
    try:
        validate_point(value)
    except InvalidTripGeometryError as exc:
        raise HTTPException(400, "Malformed geometry or invalid JSON") from exc


@router.post("", status_code=201)
async def create_trip_route(request: Request):
    try:
        payload = TripCreate.model_validate(await request.json())
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(400, "Malformed geometry or invalid JSON") from exc
    _ordered(payload.start_ts, payload.end_ts)
    _geometry(payload.start_geom)
    _geometry(payload.end_geom)
    pool, connection = _connection(request)
    try:
        try:
            return create_trip(connection, **payload.model_dump())
        except TripVehicleNotFoundError as exc:
            raise HTTPException(404, "vehicle_id does not exist") from exc
        except InvalidTripGeometryError as exc:
            raise HTTPException(400, "Malformed geometry or invalid JSON") from exc
    finally:
        pool.putconn(connection)


@router.get("")
def list_trips_route(request: Request, limit: str = "20", offset: str = "0",
                     vehicle_id: str | None = None, from_ts: str | None = None,
                     to_ts: str | None = None):
    limit_value = _integer(limit, "limit")
    offset_value = _integer(offset, "offset")
    vehicle_value = _integer(vehicle_id, "vehicle_id", True) if vehicle_id else None
    from_value, to_value = _time(from_ts, "from_ts"), _time(to_ts, "to_ts")
    if from_value and to_value:
        _ordered(from_value, to_value)
    pool, connection = _connection(request)
    try:
        items, count = get_trips(connection, limit_value, offset_value, vehicle_value, from_value, to_value)
    finally:
        pool.putconn(connection)
    return {"items": items, "limit": limit_value, "offset": offset_value, "count": count}


@router.get("/{trip_id}")
def get_trip_route(request: Request, trip_id: str):
    pool, connection = _connection(request)
    try:
        try:
            return get_trip(connection, _integer(trip_id, "trip_id", True))
        except TripNotFoundError as exc:
            raise HTTPException(404, "trip_id does not exist") from exc
    finally:
        pool.putconn(connection)


@router.put("/{trip_id}")
async def update_trip_route(request: Request, trip_id: str):
    trip_id_value = _integer(trip_id, "trip_id", True)
    try:
        payload = TripUpdate.model_validate(await request.json())
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(400, "Malformed JSON or empty patch payload") from exc
    except ValidationError as exc:
        raise HTTPException(422, "Validation failed") from exc
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "Malformed JSON or empty patch payload")
    _geometry(data.get("start_geom"))
    _geometry(data.get("end_geom"))
    pool, connection = _connection(request)
    try:
        try:
            current = get_trip(connection, trip_id_value)
            start = data.get("start_ts", datetime.fromisoformat(current["start_ts"].replace("Z", "+00:00")))
            end = data.get("end_ts", datetime.fromisoformat(current["end_ts"].replace("Z", "+00:00")))
            _ordered(start, end)
            return update_trip(connection, trip_id_value, data)
        except TripNotFoundError as exc:
            raise HTTPException(404, "trip_id does not exist") from exc
        except TripVehicleNotFoundError as exc:
            raise HTTPException(404, "vehicle_id does not exist") from exc
    finally:
        pool.putconn(connection)


@router.delete("/{trip_id}")
def delete_trip_route(request: Request, trip_id: str):
    pool, connection = _connection(request)
    try:
        try:
            return delete_trip(connection, _integer(trip_id, "trip_id", True))
        except TripNotFoundError as exc:
            raise HTTPException(404, "trip_id does not exist") from exc
    finally:
        pool.putconn(connection)


@vehicle_trips_router.get("/{vehicle_id}/trips")
def vehicle_trips_route(request: Request, vehicle_id: str, limit: str = "20",
                        offset: str = "0", from_ts: str | None = None,
                        to_ts: str | None = None):
    vehicle_value = _integer(vehicle_id, "vehicle_id", True)
    limit_value, offset_value = _integer(limit, "limit"), _integer(offset, "offset")
    from_value, to_value = _time(from_ts, "from_ts"), _time(to_ts, "to_ts")
    if from_value and to_value:
        _ordered(from_value, to_value)
    pool, connection = _connection(request)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM vehicle WHERE vehicle_id = %s", (vehicle_value,))
            if cursor.fetchone() is None:
                raise HTTPException(404, "vehicle_id does not exist")
        items, count = get_trips(connection, limit_value, offset_value, vehicle_value, from_value, to_value)
    finally:
        pool.putconn(connection)
    return {"vehicle_id": vehicle_value, "items": items, "limit": limit_value,
            "offset": offset_value, "count": count}
