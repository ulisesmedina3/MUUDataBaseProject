from __future__ import annotations

from datetime import datetime
from typing import Any

from api.v1.dao.time_format import format_timestamp


class AssignmentNotFoundError(Exception):
    """Raised when an assignment does not exist."""


class AssignmentReferenceNotFoundError(Exception):
    """Raised when a vehicle or driver does not exist."""


def _from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "assignment_id": row[0],
        "vehicle_id": row[1],
        "driver_id": row[2],
        "assigned_from": format_timestamp(row[3]),
        "assigned_to": format_timestamp(row[4]) if row[4] else None,
    }


def _check_references(cursor: Any, vehicle_id: int, driver_id: int) -> None:
    cursor.execute(
        """
        SELECT EXISTS (SELECT 1 FROM vehicle WHERE vehicle_id = %s),
               EXISTS (SELECT 1 FROM driver WHERE driver_id = %s)
        """,
        (vehicle_id, driver_id),
    )
    vehicle_exists, driver_exists = cursor.fetchone()
    if not vehicle_exists or not driver_exists:
        raise AssignmentReferenceNotFoundError


def create_assignment(connection: Any, vehicle_id: int, driver_id: int,
                      assigned_from: datetime, assigned_to: datetime | None) -> dict[str, Any]:
    with connection:
        with connection.cursor() as cursor:
            _check_references(cursor, vehicle_id, driver_id)
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('vehicle_assignment.assignment_id'))")
            cursor.execute("SELECT COALESCE(MAX(assignment_id), 0) + 1 FROM vehicle_assignment")
            assignment_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO vehicle_assignment
                    (assignment_id, vehicle_id, driver_id, assigned_from, assigned_to)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING assignment_id, vehicle_id, driver_id, assigned_from, assigned_to
                """,
                (assignment_id, vehicle_id, driver_id, assigned_from, assigned_to),
            )
            return _from_row(cursor.fetchone())


def get_assignments(connection: Any, limit: int, offset: int,
                    vehicle_id: int | None = None, driver_id: int | None = None,
                    active: bool | None = None) -> tuple[list[dict[str, Any]], int]:
    filters: list[str] = []
    parameters: list[Any] = []
    if vehicle_id is not None:
        filters.append("vehicle_id = %s")
        parameters.append(vehicle_id)
    if driver_id is not None:
        filters.append("driver_id = %s")
        parameters.append(driver_id)
    if active is True:
        filters.append("assigned_to IS NULL")
    elif active is False:
        filters.append("assigned_to IS NOT NULL")
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM vehicle_assignment {where_clause}", parameters)
        count = cursor.fetchone()[0]
        cursor.execute(
            f"""
            SELECT assignment_id, vehicle_id, driver_id, assigned_from, assigned_to
            FROM vehicle_assignment {where_clause}
            ORDER BY assignment_id LIMIT %s OFFSET %s
            """,
            [*parameters, limit, offset],
        )
        rows = cursor.fetchall()
    return [_from_row(row) for row in rows], count


def get_assignment(connection: Any, assignment_id: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT assignment_id, vehicle_id, driver_id, assigned_from, assigned_to
            FROM vehicle_assignment WHERE assignment_id = %s
            """,
            (assignment_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise AssignmentNotFoundError
    return _from_row(row)


def update_assignment(connection: Any, assignment_id: int, data: dict[str, Any]) -> dict[str, Any]:
    expressions = {
        "vehicle_id": "vehicle_id = %s",
        "driver_id": "driver_id = %s",
        "assigned_from": "assigned_from = %s",
        "assigned_to": "assigned_to = %s",
    }
    if not data:
        raise ValueError("Empty update payload")
    updates = []
    parameters: list[Any] = []
    for field, value in data.items():
        if field not in expressions:
            raise ValueError("Invalid update field")
        updates.append(expressions[field])
        parameters.append(value)
    parameters.append(assignment_id)
    with connection:
        with connection.cursor() as cursor:
            if "vehicle_id" in data or "driver_id" in data:
                cursor.execute(
                    "SELECT vehicle_id, driver_id FROM vehicle_assignment WHERE assignment_id = %s",
                    (assignment_id,),
                )
                current = cursor.fetchone()
                if current is None:
                    raise AssignmentNotFoundError
                _check_references(cursor, data.get("vehicle_id", current[0]), data.get("driver_id", current[1]))
            cursor.execute(
                f"""
                UPDATE vehicle_assignment SET {", ".join(updates)}
                WHERE assignment_id = %s
                RETURNING assignment_id, vehicle_id, driver_id, assigned_from, assigned_to
                """,
                parameters,
            )
            row = cursor.fetchone()
    if row is None:
        raise AssignmentNotFoundError
    return _from_row(row)


def delete_assignment(connection: Any, assignment_id: int) -> dict[str, Any]:
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM vehicle_assignment WHERE assignment_id = %s RETURNING assignment_id",
                (assignment_id,),
            )
            row = cursor.fetchone()
    if row is None:
        raise AssignmentNotFoundError
    return {"message": "Vehicle assignment deleted successfully.", "assignment_id": row[0]}
