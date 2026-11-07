
from __future__ import annotations

import math
import json

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import ValidationError
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.location_ping import (
    InvalidPingGeometryError,
    PingReferenceNotFoundError,
    VehicleReferenceNotFoundError,
    create_location_ping,
    get_location_ping,
    get_location_ping_by_id,
    update_location_ping,
    delete_location_ping,
    get_vehicle_pings,
)


class Location_Ping_Create(BaseModel):
    vehicle_id: int = Field(gt=0)
    ts: datetime
    geom: dict[str, Any]
    speed_kph: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    heading_deg: float | None = Field(default=None, ge=0, lt=360, allow_inf_nan=False)

    @field_validator("ts")
    @classmethod
    def validate_ts(cls, value: datetime) -> datetime:
        return value


class Location_Ping_Update(BaseModel):
    vehicle_id: int | None = Field(default=None, gt=0)
    ts: datetime | None = None
    geom: dict[str, Any] | None = None
    speed_kph: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    heading_deg: float | None = Field(default=None, ge=0, lt=360, allow_inf_nan=False)

    @field_validator("vehicle_id", "ts", "geom")
    @classmethod
    def validate_not_none(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


router = APIRouter(
    prefix="/api/v1/location-pings",
    tags=["location-ping"]
)

vehicle_pings_router = APIRouter(
    prefix="/api/v1/vehicles",
    tags=["location-ping"]
)


def parse_bbox(
    bbox: str | None,
) -> tuple[float, float, float, float] | None:

    if bbox is None:
        return None

    try:
        values = [float(x) for x in bbox.split(",")]

        if len(values) != 4:
            raise ValueError

        if not all(math.isfinite(x) for x in values):
            raise ValueError

        min_lon, min_lat, max_lon, max_lat = values

        if not (
            -180 <= min_lon < max_lon <= 180
            and -90 <= min_lat < max_lat <= 90
        ):
            raise ValueError

        return min_lon, min_lat, max_lon, max_lat

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid query parameter values.",
        ) from exc


def parse_timestamp(ts: str | None) -> datetime | None:

    if ts is None:
        return None

    try:
        return datetime.fromisoformat(
            ts.replace("Z", "+00:00")
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid query parameter values.",
        ) from exc


def validate_time_range(
    from_ts: datetime | None,
    to_ts: datetime | None,
) -> None:

    if from_ts is not None and to_ts is not None:

        start = from_ts
        end = to_ts

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        if start > end:
            raise HTTPException(
                status_code=400,
                detail="Invalid time range"
            )


def _get_connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return pool, pool.getconn()


# GET ALL LOCATION PINGS

@router.get("")
def get_location_ping_route(
    request: Request,
    limit: Annotated[int, Query(ge=0)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    vehicle_id: int | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    bbox: str | None = None,
):

    if vehicle_id is not None and vehicle_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="vehicle_id must be a positive integer"
        )

    from_value = parse_timestamp(from_ts)
    to_value = parse_timestamp(to_ts)

    validate_time_range(from_value, to_value)
    bbox_values = parse_bbox(bbox)

    pool, connection = _get_connection(request)

    try:
        items, count = get_location_ping(
            connection,
            limit,
            offset,
            vehicle_id,
            from_value.isoformat() if from_value else None,
            to_value.isoformat() if to_value else None,
            bbox_values,
        )

    finally:
        pool.putconn(connection)

    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "count": count,
    }


@router.get("/{ping_id}")
def get_location_ping_by_id_route(
    request: Request,
    ping_id: int,
):

    if ping_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="ping_id must be a positive integer"
        )

    pool, connection = _get_connection(request)

    try:
        ping = get_location_ping_by_id(connection, ping_id)

    except PingReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="ping_id does not exist"
        )

    finally:
        pool.putconn(connection)

    return ping

@vehicle_pings_router.get("/{vehicle_id}/pings")
def get_vehicle_pings_route(
    request: Request,
    vehicle_id: int,
    limit: Annotated[int, Query(ge=0)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    from_ts: str | None = None,
    to_ts: str | None = None,
):

    if vehicle_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="vehicle_id must be a positive integer"
        )

    from_value = parse_timestamp(from_ts)
    to_value = parse_timestamp(to_ts)

    validate_time_range(from_value, to_value)

    pool, connection = _get_connection(request)

    try:
        items, count = get_vehicle_pings(
            connection,
            vehicle_id,
            limit,
            offset,
            from_value.isoformat() if from_value else None,
            to_value.isoformat() if to_value else None,
        )

    except VehicleReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="vehicle_id does not exist"
        )

    finally:
        pool.putconn(connection)

    return {
        "vehicle_id": vehicle_id,
        "items": items,
        "limit": limit,
        "offset": offset,
        "count": count,
    }

@router.post("", status_code=201)
async def create_location_ping_route(request: Request):

    try:
        data = await request.json()
        payload = Location_Ping_Create.model_validate(data)

    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Malformed geometry or invalid JSON",
        ) from exc

    pool, connection = _get_connection(request)

    try:
        try:
            ping = create_location_ping(
                connection,
                payload.vehicle_id,
                payload.ts,
                payload.geom,
                payload.speed_kph,
                payload.heading_deg,
            )

        except InvalidPingGeometryError as exc:
            raise HTTPException(
                status_code=400,
                detail="Malformed geometry or invalid JSON",
            ) from exc

        except VehicleReferenceNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="vehicle_id does not exist",
            ) from exc

    finally:
        pool.putconn(connection)

    return ping


@router.put("/{ping_id}")
async def update_location_ping_route(
    request: Request,
    ping_id: int,
):

    if ping_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="ping_id must be a positive integer"
        )

    try:
        data = await request.json()
        ping = Location_Ping_Update.model_validate(data)

    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Malformed JSON or invalid update payload"
        ) from exc

    data = ping.model_dump(exclude_unset=True)

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Malformed JSON or empty patch payload."
        )

    pool, connection = _get_connection(request)

    try:
        result = update_location_ping(
            connection,
            ping_id,
            data,
        )

    except PingReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="ping_id does not exist"
        )

    except VehicleReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="vehicle_id does not exist"
        )

    except InvalidPingGeometryError:
        raise HTTPException(
            status_code=400,
            detail="Malformed geometry or invalid JSON"
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        ) from exc

    finally:
        pool.putconn(connection)

    return result

@router.delete("/{ping_id}")
def delete_location_ping_route(
    request: Request,
    ping_id: int,
):

    if ping_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="ping_id must be a positive integer"
        )

    pool, connection = _get_connection(request)

    try:
        result = delete_location_ping(connection, ping_id)

    except PingReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="ping_id does not exist"
        )

    finally:
        pool.putconn(connection)

    return result


