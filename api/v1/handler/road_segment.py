from __future__ import annotations

import math

from typing import Annotated, Any
import json
from pydantic import ValidationError
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.road_segment import (
    InvalidRoadGeometryError,
    RoadReferenceNotFoundError,
    create_road_segment,
    get_road_segment,
    get_road_segment_geojson,
    get_road_segment_by_id,
    update_road_segment,
    delete_road_segment
)


class Road_Segment_Create(BaseModel):
    name: str = Field(min_length=1)
    speed_limit_kph: int | None = Field(default=None, ge=0)
    is_oneway: bool = False
    direction: str = "both"
    geom: dict[str, Any]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty")
        return value

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, value: str) -> str:
        if value not in ("both", "forward"):
            raise ValueError("Direction must be 'both' or 'forward'")
        return value


class Road_Segment_Update(BaseModel):
    name: str | None = None
    speed_limit_kph: int | None = Field(default=None, ge=0)
    is_oneway: bool | None = None
    direction: str | None = None
    geom: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("Name cannot be empty")
        return value.strip()

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, value: str | None) -> str:
        if value not in ("both", "forward"):
            raise ValueError("Invalid direction")
        return value

    @field_validator("is_oneway", "geom")
    @classmethod
    def validate_not_none(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


router = APIRouter(prefix="/api/v1/road-segments", tags=["road-segment"])

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
            detail="Invalid bbox",
        ) from exc
    
def _get_connection(request: Request) -> tuple[ThreadedConnectionPool, Any]:
    pool: ThreadedConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    return pool, pool.getconn()


@router.get("")
def get_road_segment_route(
    request: Request,
    limit: Annotated[int, Query(ge=0)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    name: str | None = None,
    min_speed_kph: int | None = None,
    max_speed_kph: int | None = None,
    bbox: str | None = None,
):

    if (
        min_speed_kph is not None
        and max_speed_kph is not None
        and min_speed_kph > max_speed_kph
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid speed range"
        )
    
    pool, connection = _get_connection(request)
    try:
        bbox_values = parse_bbox(bbox)

        items, count = get_road_segment(
            connection,
            limit,
            offset,
            name,
            min_speed_kph,
            max_speed_kph,
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


@router.get("/geojson")
def get_road_segment_geojson_route(
    request: Request,
    limit: Annotated[int, Query(ge=0)] = 15000,
    offset: Annotated[int, Query(ge=0)] = 0,
    name: str | None = None,
    min_speed_kph: int | None = None,
    max_speed_kph: int | None = None,
    bbox: str | None = None,
):

    if (
        min_speed_kph is not None
        and max_speed_kph is not None
        and min_speed_kph > max_speed_kph
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid speed range"
        )

    bbox_values = parse_bbox(bbox)

    pool, connection = _get_connection(request)

    try:
        features, count = get_road_segment_geojson(
            connection,
            limit,
            offset,
            name,
            min_speed_kph,
            max_speed_kph,
            bbox_values,
        )
    finally:
        pool.putconn(connection)

    return {
        "type": "FeatureCollection",
        "count": count,
        "limit": limit,
        "offset": offset,
        "features": features,
    }

@router.get("/{road_id}")
def get_road_segment_by_id_route(
    request: Request,
    road_id: int,
):
    if road_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="road_id must be a positive integer"
        )

    pool, connection = _get_connection(request)

    try:
        road = get_road_segment_by_id(connection, road_id)

    except RoadReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="road_id does not exist"
        )

    finally:
        pool.putconn(connection)

    return road

@router.post("", status_code=201)
async def create_road_segment_route(request: Request):

    try:
        data = await request.json()
        payload = Road_Segment_Create.model_validate(data)

    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Malformed geometry or invalid JSON",
        ) from exc

    pool, connection = _get_connection(request)

    try:
        try:
            road_segment = create_road_segment(
                connection,
                payload.name,
                payload.speed_limit_kph,
                payload.is_oneway,
                payload.direction,
                payload.geom,
            )

        except InvalidRoadGeometryError as exc:
            raise HTTPException(
                status_code=400,
                detail="Malformed geometry or invalid JSON",
            ) from exc

    finally:
        pool.putconn(connection)

    return road_segment


@router.put("/{road_id}")
async def update_road_segment_route(
    request: Request,
    road_id: int,
):
    if road_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="road_id must be a positive integer"
        )

    try:
        data = await request.json()
        road = Road_Segment_Update.model_validate(data)

    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Malformed JSON or empty patch payload"
        ) from exc

    data = road.model_dump(exclude_unset=True)

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Malformed JSON or empty patch payload"
        )

    pool, connection = _get_connection(request)

    try:
        result = update_road_segment(
            connection,
            road_id,
            data,
        )

    except RoadReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="road_id does not exist"
        )

    except InvalidRoadGeometryError:
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

    
@router.delete("/{road_id}")
def delete_road_segment_route(
    request: Request,
    road_id: int,
):
    if road_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="road_id must be a positive integer"
        )

    pool, connection = _get_connection(request)

    try:
        result = delete_road_segment(connection, road_id)

    except RoadReferenceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="road_id does not exist"
        )

    finally:
        pool.putconn(connection)

    return result
