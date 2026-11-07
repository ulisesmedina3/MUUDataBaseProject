from __future__ import annotations

from typing import Any

import json
import psycopg2
from fastapi.responses import JSONResponse

class InvalidRoadGeometryError(Exception):
    """Raised when the road geometry is invalid."""


class RoadReferenceNotFoundError(Exception):
    """Raised when a road id does not exist."""

def get_road_segment(
    connection: Any,
    limit: int,
    offset: int,
    name: str | None = None,
    min_speed_kph: int | None = None,
    max_speed_kph: int | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    filters: list[str] = []
    parameters: list[Any] = []

    if name is not None:
        filters.append("name ILIKE %s")
        parameters.append(f"%{name}%")

    if min_speed_kph is not None:
        filters.append("speed_limit_kph >= %s")
        parameters.append(min_speed_kph)

    if max_speed_kph is not None:
        filters.append("speed_limit_kph <= %s")
        parameters.append(max_speed_kph)

    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox

        filters.append(
                """
              ST_Intersects(
                geom,
                ST_MakeEnvelope(%s, %s, %s, %s, 4326)
              )
                """
            )
        parameters.extend(
                [min_lon, min_lat, max_lon, max_lat]
            )


    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM road_segment
            {where_clause}
            """,
            parameters,
        )
        count = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT road_id, name, speed_limit_kph, created_at
            FROM road_segment
            {where_clause}
            ORDER BY road_id
            LIMIT %s OFFSET %s
            """,
            [*parameters, limit, offset],
        )
        rows = cursor.fetchall()

    road_segment = [
        {
            "road_id": row[0],
            "name": row[1],
            "speed_limit_kph": row[2],
            "created_at": row[3].isoformat(),
        }
        for row in rows
    ]
    return road_segment, count



@router.get("/geojson")
def get_road_segment_geojson_route(
    request: Request,
    limit: Annotated[int, Query(ge=0)] = 15000,
    offset: Annotated[int, Query(ge=0)] = 0,
    name: str | None = None,
    min_speed_kph: Annotated[int | None, Query(ge=0)] = None,
    max_speed_kph: Annotated[int | None, Query(ge=0)] = None,
    bbox: str | None = None,
):

    if (
        min_speed_kph is not None
        and max_speed_kph is not None
        and min_speed_kph > max_speed_kph
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid or inconsistent filter values"
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

    return JSONResponse(
        content={
            "type": "FeatureCollection",
            "count": count,
            "limit": limit,
            "offset": offset,
            "features": features,
        },
        media_type="application/geo+json",
    )

def get_road_segment_by_id(
    connection: Any,
    road_id: int,
) -> dict[str, Any]:

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT road_id, name, speed_limit_kph,
                   ST_AsGeoJSON(geom), created_at
            FROM road_segment
            WHERE road_id = %s
            """,
            (road_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise RoadReferenceNotFoundError(
            "road_id does not exist"
        )

    return {
        "road_id": row[0],
        "name": row[1],
        "speed_limit_kph": row[2],
        "geom": json.loads(row[3]),
        "created_at": row[4].isoformat(),
    }

def update_road_segment(
    connection: Any,
    road_id: int,
    data: dict[str, Any],
) -> dict[str, Any]:

    if not data:
        raise ValueError("Empty patch payload")

    fields = {
        "name": "name = %s",
        "speed_limit_kph": "speed_limit_kph = %s",
        "is_oneway": "is_oneway = %s",
        "direction": "direction = %s",
        "geom": "geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)",
    }

    updates = []
    parameters = []

    for field, value in data.items():
        if field not in fields:
            raise ValueError("Invalid update field")

        updates.append(fields[field])

        if field == "geom":
            if not isinstance(value, dict) or value.get("type") != "LineString":
                raise InvalidRoadGeometryError("Invalid road geometry")
            parameters.append(json.dumps(value))
        else:
            parameters.append(value)

    parameters.append(road_id)

    try:
        with connection:
            with connection.cursor() as cursor:

                if "geom" in data:
                    cursor.execute(
                        """
                        SELECT
                            ST_IsValid(g)
                            AND NOT ST_IsEmpty(g)
                            AND ST_GeometryType(g) = 'ST_LineString'
                        FROM (
                            SELECT ST_SetSRID(
                                ST_GeomFromGeoJSON(%s), 4326
                            ) AS g
                        ) AS geometry_check
                        """,
                        (json.dumps(data["geom"]),),
                    )

                    if cursor.fetchone()[0] is not True:
                        raise InvalidRoadGeometryError(
                            "Invalid road geometry"
                        )

                cursor.execute(
                    f"""
                    UPDATE road_segment
                    SET {", ".join(updates)}
                    WHERE road_id = %s
                    RETURNING road_id, name, speed_limit_kph,
                              ST_AsGeoJSON(geom), created_at
                    """,
                    parameters,
                )

                row = cursor.fetchone()

                if row is None:
                    raise RoadReferenceNotFoundError(
                        "road_id does not exist"
                    )

    except (
        psycopg2.errors.InvalidParameterValue,
        psycopg2.errors.InvalidTextRepresentation,
    ) as exc:
        raise InvalidRoadGeometryError(
            "Invalid road geometry"
        ) from exc

    return {
        "road_id": row[0],
        "name": row[1],
        "speed_limit_kph": row[2],
        "geom": json.loads(row[3]),
        "created_at": row[4].isoformat(),
    }



def create_road_segment(
    connection: Any,
    name: str,
    speed_limit_kph: int | None,
    is_oneway: bool,
    direction: str,
    geom: dict[str, Any],
) -> dict[str, Any]:

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtext('road_segment.road_id')
                    )
                    """
                )
                cursor.execute("SELECT COALESCE(MAX(road_id), 0) + 1 FROM road_segment")
                road_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO road_segment (
                        road_id, name, speed_limit_kph,
                        is_oneway, direction, geom, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        ST_SetSRID(
                            ST_GeomFromGeoJSON(%s),
                            4326
                        ),
                        CURRENT_TIMESTAMP
                    )
                    RETURNING road_id, name, speed_limit_kph, is_oneway, direction,
                              ST_AsGeoJSON(geom), created_at
                    """,
                    (
                        road_id,
                        name,
                        speed_limit_kph,
                        is_oneway,
                        direction,
                        json.dumps(geom),
                    ),
                )
                row = cursor.fetchone()
    except (
        psycopg2.errors.InvalidParameterValue,
        psycopg2.errors.InvalidTextRepresentation,
    ) as exc:
        raise InvalidRoadGeometryError(
            "Invalid road geometry"
        ) from exc

    return {
        "road_id": row[0],
        "name": row[1],
        "speed_limit_kph": row[2],
        "is_oneway": row[3],
        "direction": row[4],
        "geom": json.loads(row[5]),
        "created_at": row[6].isoformat(),
    }

def delete_road_segment(
    connection: Any,
    road_id: int,
) -> dict[str, Any]:

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM road_segment
                WHERE road_id = %s
                RETURNING road_id
                """,
                (road_id,),
            )

            row = cursor.fetchone()

            if row is None:
                raise RoadReferenceNotFoundError(
                    "road_id does not exist"
                )

    return {
        "message": "Road segment deleted successfully.",
        "road_id": row[0],
    }