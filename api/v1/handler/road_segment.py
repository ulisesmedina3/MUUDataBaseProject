from __future__ import annotations

import math

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from psycopg2.pool import ThreadedConnectionPool

from api.v1.dao.road_segment import (
    InvalidRoadGeometryError,
    RoadReferenceNotFoundError,
    create_road_segment,
    get_road_segment,
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


@router.post("", status_code=201)
def create_road_segment_route(payload: Road_Segment_Create, request: Request):
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
        except RoadReferenceNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="road_id does not exist",
            ) from exc
        except InvalidRoadGeometryError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid geometry already exists",
            ) from exc
    finally:
        pool.putconn(connection)

    return road_segment
