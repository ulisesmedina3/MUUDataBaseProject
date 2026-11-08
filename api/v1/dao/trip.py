from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from api.v1.dao.time_format import format_timestamp


class TripNotFoundError(Exception):
    """Raised when a trip does not exist."""


class TripVehicleNotFoundError(Exception):
    """Raised when a referenced vehicle does not exist."""


class InvalidTripGeometryError(Exception):
    """Raised when a trip geometry is invalid."""


def validate_point(geom: dict[str, Any] | None) -> None:
    if geom is None:
        return
    coordinates = geom.get("coordinates") if isinstance(geom, dict) else None
    if (
        geom.get("type") != "Point"
        or not isinstance(coordinates, list)
        or len(coordinates) != 2
        or type(coordinates[0]) not in (int, float)
        or type(coordinates[1]) not in (int, float)
        or not -180 <= coordinates[0] <= 180
        or not -90 <= coordinates[1] <= 90
    ):
        raise InvalidTripGeometryError


def _from_row(row: tuple[Any, ...], geometry: bool = True) -> dict[str, Any]:
    result = {
        "trip_id": row[0],
        "vehicle_id": row[1],
        "start_ts": format_timestamp(row[2]),
        "end_ts": format_timestamp(row[3]),
    }
    if geometry:
        result["start_geom"] = json.loads(row[4]) if row[4] else None
        result["end_geom"] = json.loads(row[5]) if row[5] else None
    result["distance_km"] = row[6]
    return result


def create_trip(connection: Any, vehicle_id: int, start_ts: datetime, end_ts: datetime,
                start_geom: dict[str, Any] | None, end_geom: dict[str, Any] | None,
                distance_km: float | None) -> dict[str, Any]:
    validate_point(start_geom)
    validate_point(end_geom)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM vehicle WHERE vehicle_id = %s", (vehicle_id,))
            if cursor.fetchone() is None:
                raise TripVehicleNotFoundError
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('trip.trip_id'))")
            cursor.execute("SELECT COALESCE(MAX(trip_id), 0) + 1 FROM trip")
            trip_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO trip (trip_id, vehicle_id, start_ts, end_ts,
                                  start_geom, end_geom, distance_km)
                VALUES (%s, %s, %s, %s,
                        ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                        ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s)
                RETURNING trip_id, vehicle_id, start_ts, end_ts,
                          ST_AsGeoJSON(start_geom), ST_AsGeoJSON(end_geom),
                          distance_km
                """,
                (trip_id, vehicle_id, start_ts, end_ts,
                 json.dumps(start_geom) if start_geom else None,
                 json.dumps(end_geom) if end_geom else None, distance_km),
            )
            return _from_row(cursor.fetchone())


def _query(
    connection: Any, limit: int, offset: int, vehicle_id: int | None,
    from_ts: datetime | None, to_ts: datetime | None,
) -> tuple[list[dict[str, Any]], int]:
    filters: list[str] = []
    params: list[Any] = []
    if vehicle_id is not None:
        filters.append("vehicle_id = %s")
        params.append(vehicle_id)
    if from_ts is not None:
        filters.append("start_ts >= %s")
        params.append(from_ts)
    if to_ts is not None:
        filters.append("start_ts <= %s")
        params.append(to_ts)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM trip {where}", params)
        count = cursor.fetchone()[0]
        cursor.execute(
            f"""SELECT trip_id, vehicle_id, start_ts, end_ts, NULL, NULL, distance_km
                FROM trip {where} ORDER BY trip_id LIMIT %s OFFSET %s""",
            [*params, limit, offset],
        )
        return [_from_row(row, False) for row in cursor.fetchall()], count


def get_trips(connection: Any, limit: int, offset: int, vehicle_id: int | None = None,
              from_ts: datetime | None = None, to_ts: datetime | None = None):
    return _query(connection, limit, offset, vehicle_id, from_ts, to_ts)


def get_trip(connection: Any, trip_id: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT trip_id, vehicle_id, start_ts, end_ts,
                      ST_AsGeoJSON(start_geom), ST_AsGeoJSON(end_geom), distance_km
               FROM trip WHERE trip_id = %s""",
            (trip_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise TripNotFoundError
    return _from_row(row)


def update_trip(connection: Any, trip_id: int, data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        raise ValueError("Empty patch payload")
    expressions = {
        "vehicle_id": "vehicle_id = %s", "start_ts": "start_ts = %s",
        "end_ts": "end_ts = %s",
        "start_geom": "start_geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)",
        "end_geom": "end_geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)",
        "distance_km": "distance_km = %s",
    }
    updates = []
    params: list[Any] = []
    for field, value in data.items():
        if field not in expressions:
            raise ValueError("Invalid update field")
        updates.append(expressions[field])
        params.append(json.dumps(value) if field.endswith("_geom") else value)
    params.append(trip_id)
    with connection:
        with connection.cursor() as cursor:
            if "vehicle_id" in data:
                cursor.execute("SELECT 1 FROM vehicle WHERE vehicle_id = %s", (data["vehicle_id"],))
                if cursor.fetchone() is None:
                    raise TripVehicleNotFoundError
            cursor.execute(
                f"""UPDATE trip SET {", ".join(updates)} WHERE trip_id = %s
                    RETURNING trip_id, vehicle_id, start_ts, end_ts,
                              ST_AsGeoJSON(start_geom), ST_AsGeoJSON(end_geom), distance_km""",
                params,
            )
            row = cursor.fetchone()
    if row is None:
        raise TripNotFoundError
    return _from_row(row)


def delete_trip(connection: Any, trip_id: int) -> dict[str, Any]:
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM trip WHERE trip_id = %s RETURNING trip_id", (trip_id,))
            row = cursor.fetchone()
    if row is None:
        raise TripNotFoundError
    return {"message": "Trip deleted successfully.", "trip_id": row[0]}
