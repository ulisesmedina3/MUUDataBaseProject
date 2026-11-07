
from __future__ import annotations

from typing import Any

import json
import math
import psycopg2


class InvalidPingGeometryError(Exception):
    """Raised when the ping geometry is invalid."""


class PingReferenceNotFoundError(Exception):
    """Raised when a ping_id does not exist."""


class VehicleReferenceNotFoundError(Exception):
    """Raised when a referenced vehicle_id does not exist."""


def validate_ping_geometry(geom: dict[str, Any]) -> None:
    """Validate Point geometry and WGS84 coordinates."""

    if not isinstance(geom, dict) or geom.get("type") != "Point":
        raise InvalidPingGeometryError("Invalid ping geometry")

    coordinates = geom.get("coordinates")

    if not isinstance(coordinates, list) or len(coordinates) != 2:
        raise InvalidPingGeometryError("Invalid ping geometry")

    lon, lat = coordinates

    if type(lon) not in (int, float) or type(lat) not in (int, float):
        raise InvalidPingGeometryError("Invalid ping geometry")

    if not math.isfinite(lon) or not math.isfinite(lat):
        raise InvalidPingGeometryError("Invalid ping geometry")

    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise InvalidPingGeometryError("Invalid ping geometry")

def get_location_ping(
    connection: Any,
    limit: int,
    offset: int,
    vehicle_id: int | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> tuple[list[dict[str, Any]], int]:

    filters: list[str] = []
    parameters: list[Any] = []

    if vehicle_id is not None:
        filters.append("vehicle_id = %s")
        parameters.append(vehicle_id)

    if from_ts is not None:
        filters.append("ts >= %s")
        parameters.append(from_ts)

    if to_ts is not None:
        filters.append("ts <= %s")
        parameters.append(to_ts)

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
            FROM location_ping
            {where_clause}
            """,
            parameters,
        )
        count = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT ping_id, vehicle_id, ts,
                   speed_kph, heading_deg
            FROM location_ping
            {where_clause}
            ORDER BY ping_id
            LIMIT %s OFFSET %s
            """,
            [*parameters, limit, offset],
        )
        rows = cursor.fetchall()

    location_pings = [
        {
            "ping_id": row[0],
            "vehicle_id": row[1],
            "ts": row[2].isoformat(),
            "speed_kph": row[3],
            "heading_deg": row[4],
        }
        for row in rows
    ]

    return location_pings, count


# GET LOCATION PING BY ID

def get_location_ping_by_id(
    connection: Any,
    ping_id: int,
) -> dict[str, Any]:

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ping_id, vehicle_id, ts,
                   ST_AsGeoJSON(geom), speed_kph, heading_deg
            FROM location_ping
            WHERE ping_id = %s
            """,
            (ping_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise PingReferenceNotFoundError(
            "ping_id does not exist"
        )

    return {
        "ping_id": row[0],
        "vehicle_id": row[1],
        "ts": row[2].isoformat(),
        "geom": json.loads(row[3]),
        "speed_kph": row[4],
        "heading_deg": row[5],
    }


# CREATE LOCATION PING

def create_location_ping(
    connection: Any,
    vehicle_id: int,
    ts: Any,
    geom: dict[str, Any],
    speed_kph: float | None,
    heading_deg: float | None,
) -> dict[str, Any]:

    validate_ping_geometry(geom)

    try:
        with connection:
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT vehicle_id
                    FROM vehicle
                    WHERE vehicle_id = %s
                    """,
                    (vehicle_id,),
                )

                if cursor.fetchone() is None:
                    raise VehicleReferenceNotFoundError(
                        "vehicle_id does not exist"
                    )

                cursor.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtext('location_ping.ping_id')
                    )
                    """
                )

                cursor.execute(
                    """
                    SELECT COALESCE(MAX(ping_id), 0) + 1
                    FROM location_ping
                    """
                )
                ping_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO location_ping (
                        ping_id, vehicle_id, ts,
                        geom, speed_kph, heading_deg
                    )
                    VALUES (
                        %s, %s, %s,
                        ST_SetSRID(
                            ST_GeomFromGeoJSON(%s),
                            4326
                        ),
                        %s, %s
                    )
                    RETURNING ping_id, vehicle_id, ts,
                              ST_AsGeoJSON(geom),
                              speed_kph, heading_deg
                    """,
                    (
                        ping_id,
                        vehicle_id,
                        ts,
                        json.dumps(geom),
                        speed_kph,
                        heading_deg,
                    ),
                )
                row = cursor.fetchone()

    except psycopg2.errors.ForeignKeyViolation as exc:
        raise VehicleReferenceNotFoundError(
            "vehicle_id does not exist"
        ) from exc

    except (
        psycopg2.errors.InvalidParameterValue,
        psycopg2.errors.InvalidTextRepresentation,
    ) as exc:
        raise InvalidPingGeometryError(
            "Invalid ping geometry"
        ) from exc

    return {
        "ping_id": row[0],
        "vehicle_id": row[1],
        "ts": row[2].isoformat(),
        "geom": json.loads(row[3]),
        "speed_kph": row[4],
        "heading_deg": row[5],
    }


def update_location_ping(
    connection: Any,
    ping_id: int,
    data: dict[str, Any],
) -> dict[str, Any]:

    if not data:
			        raise ValueError("Empty patch payload")

    fields = {
        "vehicle_id": "vehicle_id = %s",
        "ts": "ts = %s",
        "geom": "geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)",
        "speed_kph": "speed_kph = %s",
        "heading_deg": "heading_deg = %s",
    }

    updates = []
    parameters = []

    for field, value in data.items():
        if field not in fields:
            raise ValueError("Invalid update field")

        updates.append(fields[field])

        if field == "geom":
            validate_ping_geometry(value)
            parameters.append(json.dumps(value))
        else:
            parameters.append(value)

    parameters.append(ping_id)

    try:
        with connection:
            with connection.cursor() as cursor:

                if "vehicle_id" in data:
                    cursor.execute(
                        """
                        SELECT vehicle_id
                        FROM vehicle
                        WHERE vehicle_id = %s
                        """,
                        (data["vehicle_id"],),
                    )

                    if cursor.fetchone() is None:
                        raise VehicleReferenceNotFoundError(
                            "vehicle_id does not exist"
                        )

                cursor.execute(
                    f"""
                    UPDATE location_ping
                    SET {", ".join(updates)}
                    WHERE ping_id = %s
                    RETURNING ping_id, vehicle_id, ts,
                              ST_AsGeoJSON(geom),
                              speed_kph, heading_deg
                    """,
                    parameters,
                )

                row = cursor.fetchone()

                if row is None:
                    raise PingReferenceNotFoundError(
                        "ping_id does not exist"
                    )

    except psycopg2.errors.ForeignKeyViolation as exc:
        raise VehicleReferenceNotFoundError(
            "vehicle_id does not exist"
        ) from exc

    except (
        psycopg2.errors.InvalidParameterValue,
        psycopg2.errors.InvalidTextRepresentation,
    ) as exc:
        raise InvalidPingGeometryError(
            "Invalid ping geometry"
        ) from exc

    return {
        "ping_id": row[0],
        "vehicle_id": row[1],
        "ts": row[2].isoformat(),
        "geom": json.loads(row[3]),
        "speed_kph": row[4],
        "heading_deg": row[5],
    }

def delete_location_ping(
    connection: Any,
    ping_id: int,
) -> dict[str, Any]:

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM location_ping
                WHERE ping_id = %s
                RETURNING ping_id
                """,
                (ping_id,),
            )

            row = cursor.fetchone()

            if row is None:
                raise PingReferenceNotFoundError(
                    "ping_id does not exist"
                )

    return {
        "message": "Location ping deleted successfully.",
        "ping_id": row[0],
    }


# GET ALL PINGS FOR ONE VEHICLE

def get_vehicle_pings(
    connection: Any,
    vehicle_id: int,
    limit: int,
    offset: int,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> tuple[list[dict[str, Any]], int]:

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT vehicle_id
            FROM vehicle
            WHERE vehicle_id = %s
            """,
            (vehicle_id,),
        )

        if cursor.fetchone() is None:
            raise VehicleReferenceNotFoundError(
                "vehicle_id does not exist"
            )

        filters = ["vehicle_id = %s"]
        parameters: list[Any] = [vehicle_id]

        if from_ts is not None:
            filters.append("ts >= %s")
            parameters.append(from_ts)

        if to_ts is not None:
            filters.append("ts <= %s")
            parameters.append(to_ts)

        where_clause = f"WHERE {' AND '.join(filters)}"

        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM location_ping
            {where_clause}
            """,
            parameters,
        )
        count = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT ping_id, ts, ST_AsGeoJSON(geom),
                   speed_kph, heading_deg
            FROM location_ping
            {where_clause}
            ORDER BY ts, ping_id
            LIMIT %s OFFSET %s
            """,
            [*parameters, limit, offset],
        )
        rows = cursor.fetchall()

    location_pings = [
        {
            "ping_id": row[0],
            "ts": row[1].isoformat(),
            "geom": json.loads(row[2]),
            "speed_kph": row[3],
            "heading_deg": row[4],
        }
        for row in rows
    ]

    return location_pings, count
