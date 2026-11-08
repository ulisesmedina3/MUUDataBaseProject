from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg2
from pydantic import BaseModel


class Driver(BaseModel):
    driver_id: int
    first_name: str | None
    last_name: str | None
    license_number: str | None
    hired_at: datetime | None


class DriverNotFoundError(Exception):
    """Raised when a driver does not exist."""


class DriverDeleteConflictError(Exception):
    """Raised when a driver is referenced by another record."""


class DriverLicenseConflictError(Exception):
    """Raised when a license number is already assigned to a driver."""


class DriverDAO:
    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> Driver:
        return Driver(
            driver_id=row[0],
            first_name=row[1],
            last_name=row[2],
            license_number=row[3],
            hired_at=row[4],
        )

    @staticmethod
    def create_driver(
        connection: Any,
        first_name: str,
        last_name: str,
        license_number: str,
        hired_at: datetime | None = None,
    ) -> Driver:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtext('driver.license_number'),
                        hashtext(LOWER(%s))
                    )
                    """,
                    (license_number,),
                )
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM driver
                        WHERE LOWER(license_number) = LOWER(%s)
                    )
                    """,
                    (license_number,),
                )
                if cursor.fetchone()[0]:
                    raise DriverLicenseConflictError

                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext('driver.driver_id'))"
                )
                cursor.execute("SELECT COALESCE(MAX(driver_id), 0) + 1 FROM driver")
                driver_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO driver (
                        driver_id, first_name, last_name, license_number, hired_at
                    )
                    VALUES (%s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP))
                    RETURNING driver_id, first_name, last_name, license_number, hired_at
                    """,
                    (driver_id, first_name, last_name, license_number, hired_at),
                )
                row = cursor.fetchone()

        return DriverDAO._from_row(row)

    @staticmethod
    def get_drivers(
        connection: Any,
        first_name: str | None = None,
        last_name: str | None = None,
        license_number: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Driver], int]:
        filters: list[str] = []
        parameters: list[Any] = []

        # Converts all string inputs to lower case and appends them to be filters for the "where clause"
        if first_name is not None:
            filters.append("LOWER(first_name) LIKE %s")
            parameters.append(f"%{first_name.lower()}%")

        if last_name is not None:
            filters.append("LOWER(last_name) LIKE %s")
            parameters.append(f"%{last_name.lower()}%")

        if license_number is not None:
            filters.append("LOWER(license_number) LIKE %s")
            parameters.append(f"%{license_number.lower()}%")

        # Generates a "where clause" for the query
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        # Actually does the query to the Postrgesql database
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM driver {where_clause}", parameters)
            count = cursor.fetchone()[0]
            cursor.execute(
                f"""
                SELECT driver_id, first_name, last_name, license_number, hired_at
                FROM driver
                {where_clause}
                ORDER BY driver_id
                LIMIT %s OFFSET %s
                """,
                [*parameters, limit, offset],
            )
            rows = cursor.fetchall()

        return [DriverDAO._from_row(row) for row in rows], count

    @staticmethod
    def get_driver_by_id(connection: Any, driver_id: int) -> Driver:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT driver_id, first_name, last_name, license_number, hired_at
                FROM driver
                WHERE driver_id = %s
                """,
                (driver_id,),
            )
            row = cursor.fetchone()

        if row is None:
            raise DriverNotFoundError
        return DriverDAO._from_row(row)

    @staticmethod
    def update_driver(
        connection: Any,
        driver_id: int,
        data: dict[str, Any],
    ) -> Driver:
        field_expressions = {
            "first_name": "first_name = %s",
            "last_name": "last_name = %s",
            "license_number": "license_number = %s",
            "hired_at": "hired_at = %s",
        }
        if not data or any(field not in field_expressions for field in data):
            raise ValueError("Invalid driver update")

        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT driver_id FROM driver WHERE driver_id = %s FOR UPDATE",
                    (driver_id,),
                )
                if cursor.fetchone() is None:
                    raise DriverNotFoundError

                if "license_number" in data:
                    license_number = data["license_number"]
                    cursor.execute(
                        """
                        SELECT pg_advisory_xact_lock(
                            hashtext('driver.license_number'),
                            hashtext(LOWER(%s))
                        )
                        """,
                        (license_number,),
                    )
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM driver
                            WHERE LOWER(license_number) = LOWER(%s)
                              AND driver_id <> %s
                        )
                        """,
                        (license_number, driver_id),
                    )
                    if cursor.fetchone()[0]:
                        raise DriverLicenseConflictError

                assignments = ", ".join(
                    field_expressions[field] for field in data
                )
                cursor.execute(
                    f"""
                    UPDATE driver
                    SET {assignments}
                    WHERE driver_id = %s
                    RETURNING driver_id, first_name, last_name, license_number, hired_at
                    """,
                    [*data.values(), driver_id],
                )
                row = cursor.fetchone()

        return DriverDAO._from_row(row)

    @staticmethod
    def delete_driver(connection: Any, driver_id: int) -> dict[str, Any]:
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM driver
                        WHERE driver_id = %s
                        RETURNING driver_id
                        """,
                        (driver_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise DriverNotFoundError
        except psycopg2.errors.ForeignKeyViolation as exc:
            raise DriverDeleteConflictError from exc

        return {
            "message": "Driver deleted successfully.",
            "driver_id": row[0],
        }
