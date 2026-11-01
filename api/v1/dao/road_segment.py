from __future__ import annotations

from typing import Any

import json
import psycopg2


class InvalidRoadGeometryError(Exception):
    """Raised when the road geometry is invalid."""


class RoadReferenceNotFoundError(Exception):
    """Raised when a road segment does not exist."""

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
