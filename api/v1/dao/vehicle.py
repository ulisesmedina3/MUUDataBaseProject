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
