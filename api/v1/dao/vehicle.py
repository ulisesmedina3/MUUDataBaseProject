from __future__ import annotations

from typing import Any

import psycopg2


class DuplicatePlateError(Exception):
    """Raised when a vehicle plate number is already registered."""


class VehicleReferenceNotFoundError(Exception):
    """Raised when a vehicle type or status does not exist."""


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
            "created_at": row[7].isoformat(),
        }
        for row in rows
    ]
    return vehicles, count


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
        "created_at": row[7],
    }
