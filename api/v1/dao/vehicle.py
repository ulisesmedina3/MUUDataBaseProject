from __future__ import annotations

import json
from typing import Any

import psycopg2


class DuplicatePlateError(Exception):
    """Raised when a vehicle plate number is already registered."""


class VehicleReferenceNotFoundError(Exception):
    """Raised when a vehicle type or status does not exist."""


class VehicleNotFoundError(Exception):
    """Raised when a vehicle does not exist."""


class VehicleDeleteConflictError(Exception):
    """Raised when a vehicle cannot be deleted because it is referenced."""


def _format_timestamp(value: Any) -> str:
    timestamp = value.isoformat()
    return timestamp if value.tzinfo is not None else f"{timestamp}Z"


def _vehicle_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "vehicle_id": row[0],
        "vehicle_type_id": row[1],
        "vehicle_status_id": row[2],
        "plate_number": row[3],
        "make": row[4],
        "model": row[5],
        "year": row[6],
        "created_at": _format_timestamp(row[7]),
    }


def ensure_vehicle_constraints(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS vehicle_plate_number_unique
            ON vehicle (plate_number)
            """
        )
    connection.commit()


def get_vehicles(
    connection: Any,
    limit: int,
    offset: int,
    status: str | None,
    plate_number: str | None,
) -> tuple[list[dict[str, Any]], int]:
    filters: list[str] = []
    parameters: list[Any] = []

    if status is not None:
        try:
            status_id = int(status)
        except ValueError:
            filters.append(
                """
                EXISTS (
                    SELECT 1
                    FROM vehicle_status AS status
                    WHERE status.vehicle_status_id = vehicle.vehicle_status_id
                      AND status.name ILIKE %s
                )
                """
            )
            parameters.append(status)
        else:
            filters.append("vehicle.vehicle_status_id = %s")
            parameters.append(status_id)

    if plate_number is not None:
        filters.append("vehicle.plate_number ILIKE %s")
        parameters.append(f"%{plate_number}%")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM vehicle
            {where_clause}
            """,
            parameters,
        )
        count = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT vehicle_id, plate_number, make, model, year,
                   vehicle_type_id, vehicle_status_id, created_at
            FROM vehicle
            {where_clause}
            ORDER BY vehicle_id
            LIMIT %s OFFSET %s
            """,
            [*parameters, limit, offset],
        )
        rows = cursor.fetchall()

    vehicles = [
        {
            "vehicle_id": row[0],
            "plate_number": row[1],
            "make": row[2],
            "model": row[3],
            "year": row[4],
            "vehicle_type_id": row[5],
            "vehicle_status_id": row[6],
            "created_at": _format_timestamp(row[7]),
        }
        for row in rows
    ]
    return vehicles, count


def get_vehicle(connection: Any, vehicle_id: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT vehicle_id, vehicle_type_id, vehicle_status_id,
                   plate_number, make, model, year, created_at
            FROM vehicle
            WHERE vehicle_id = %s
            """,
            (vehicle_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise VehicleNotFoundError
    return _vehicle_from_row(row)


def create_vehicle(
    connection: Any,
    vehicle_type_id: int,
    vehicle_status_id: int,
    plate_number: str,
    make: str | None,
    model: str | None,
    year: int,
) -> dict[str, Any]:
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        EXISTS (
                            SELECT 1 FROM vehicle_type
                            WHERE vehicle_type_id = %s
                        ),
                        EXISTS (
                            SELECT 1 FROM vehicle_status
                            WHERE vehicle_status_id = %s
                        )
                    """,
                    (vehicle_type_id, vehicle_status_id),
                )
                type_exists, status_exists = cursor.fetchone()
                if not type_exists or not status_exists:
                    raise VehicleReferenceNotFoundError

                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext('vehicle.vehicle_id'))"
                )
                cursor.execute("SELECT COALESCE(MAX(vehicle_id), 0) + 1 FROM vehicle")
                vehicle_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO vehicle (
                        vehicle_id, vehicle_type_id, vehicle_status_id,
                        plate_number, make, model, year, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING vehicle_id, vehicle_type_id, vehicle_status_id,
                              plate_number, make, model, year, created_at
                    """,
                    (
                        vehicle_id,
                        vehicle_type_id,
                        vehicle_status_id,
                        plate_number,
                        make,
                        model,
                        year,
                    ),
                )
                row = cursor.fetchone()
    except psycopg2.errors.UniqueViolation as exc:
        raise DuplicatePlateError from exc
    except psycopg2.errors.ForeignKeyViolation as exc:
        raise VehicleReferenceNotFoundError from exc

    return {
        "vehicle_id": row[0],
        "vehicle_type_id": row[1],
        "vehicle_status_id": row[2],
        "plate_number": row[3],
        "make": row[4],
        "model": row[5],
        "year": row[6],
        "created_at": _format_timestamp(row[7]),
    }


def update_vehicle(
    connection: Any,
    vehicle_id: int,
    data: dict[str, Any],
) -> dict[str, Any]:
    if not data:
        raise ValueError("At least one field must be supplied")

    allowed_fields = {
        "vehicle_type_id",
        "vehicle_status_id",
        "plate_number",
        "make",
        "model",
        "year",
    }
    fields = [field for field in data if field in allowed_fields]
    if not fields:
        raise ValueError("At least one field must be supplied")

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT vehicle_id FROM vehicle WHERE vehicle_id = %s",
                (vehicle_id,),
            )
            if cursor.fetchone() is None:
                raise VehicleNotFoundError

            if "vehicle_type_id" in data or "vehicle_status_id" in data:
                cursor.execute(
                    """
                    SELECT
                        EXISTS (
                            SELECT 1 FROM vehicle_type
                            WHERE vehicle_type_id = COALESCE(%s, vehicle.vehicle_type_id)
                        ),
                        EXISTS (
                            SELECT 1 FROM vehicle_status
                            WHERE vehicle_status_id = COALESCE(%s, vehicle.vehicle_status_id)
                        )
                    FROM vehicle
                    WHERE vehicle_id = %s
                    """,
                    (
                        data.get("vehicle_type_id"),
                        data.get("vehicle_status_id"),
                        vehicle_id,
                    ),
                )
                type_exists, status_exists = cursor.fetchone()
                if not type_exists or not status_exists:
                    raise VehicleReferenceNotFoundError

            assignments = ", ".join(f"{field} = %s" for field in fields)
            parameters = [data[field] for field in fields]
            parameters.append(vehicle_id)
            try:
                cursor.execute(
                    f"""
                    UPDATE vehicle
                    SET {assignments}
                    WHERE vehicle_id = %s
                    RETURNING vehicle_id, vehicle_type_id, vehicle_status_id,
                              plate_number, make, model, year, created_at
                    """,
                    parameters,
                )
            except psycopg2.errors.UniqueViolation as exc:
                raise DuplicatePlateError from exc
            except psycopg2.errors.ForeignKeyViolation as exc:
                raise VehicleReferenceNotFoundError from exc
            row = cursor.fetchone()

    return _vehicle_from_row(row)


def delete_vehicle(connection: Any, vehicle_id: int) -> dict[str, Any]:
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM vehicle
                    WHERE vehicle_id = %s
                    RETURNING vehicle_id
                    """,
                    (vehicle_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise VehicleNotFoundError
    except psycopg2.errors.ForeignKeyViolation as exc:
        raise VehicleDeleteConflictError from exc

    return {
        "message": "Vehicle deleted successfully.",
        "vehicle_id": row[0],
    }


def get_current_location(connection: Any, vehicle_id: int) -> dict[str, Any] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT v.vehicle_id, v.plate_number, vs.name,
                   vk.name, ft.name, vt.emissions_rating,
                   lp.ts, ST_AsGeoJSON(lp.geom),
                   lp.speed_kph, lp.heading_deg
            FROM vehicle AS v
            LEFT JOIN vehicle_status AS vs
              ON vs.vehicle_status_id = v.vehicle_status_id
            LEFT JOIN vehicle_type AS vt
              ON vt.vehicle_type_id = v.vehicle_type_id
            LEFT JOIN vehicle_kind AS vk
              ON vk.vehicle_kind_id = vt.vehicle_kind_id
            LEFT JOIN fuel_type AS ft
              ON ft.fuel_type_id = vt.fuel_type_id
            LEFT JOIN LATERAL (
                SELECT ts, geom, speed_kph, heading_deg
                FROM location_ping
                WHERE vehicle_id = v.vehicle_id
                ORDER BY ts DESC, ping_id DESC
                LIMIT 1
            ) AS lp ON TRUE
            WHERE v.vehicle_id = %s
            """,
            (vehicle_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise VehicleNotFoundError
    if row[6] is None:
        return None

    return {
        "vehicle_id": row[0],
        "plate_number": row[1],
        "status": row[2],
        "vehicle_type": row[3],
        "fuel_type": row[4],
        "emissions_rating": row[5],
        "last_ts": _format_timestamp(row[6]),
        "last_geom": json.loads(row[7]),
        "speed_kph": row[8],
        "heading_deg": row[9],
    }
