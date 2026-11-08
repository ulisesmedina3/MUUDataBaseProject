from __future__ import annotations
from typing import Any, Literal

import json
from api.v1.config.dbconfig import PG_DB_CONFIG, POOL_CONFIG
import psycopg2
from datetime import datetime
from pydantic import BaseModel, Field
from psycopg2.pool import SimpleConnectionPool

from api.v1.dao.time_format import format_timestamp

# These are the attributes of the ParkingArea table in the database
class ParkingArea(BaseModel):
    parking_area_id: int
    name: str
    capacity: int | None
    geom: str
    created_at: datetime

class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[tuple[float, float]]]

class ParkingAreaCreate(BaseModel):
    name: str = Field(min_length=1, strip_whitespace=True)
    capacity: int | None = Field(default=None, ge=0)
    geom: GeoJSONPolygon


class ParkingAreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    capacity: int | None = Field(default=None, gt=0)
    geom: GeoJSONPolygon | None = None


class ParkingAreaNotFoundError(Exception):
    """Raised when a parking area to update does not exist."""


class InvalidParkingAreaGeometryError(Exception):
    """Raised when the supplied geometry is not a valid polygon."""


class ParkingAreaDAO():
    def __init__(self):
        self.pool = SimpleConnectionPool(POOL_CONFIG["minconn"], POOL_CONFIG["maxconn"], **PG_DB_CONFIG)
    
    @staticmethod
    def create_parking_area(conn: Any, payload: ParkingAreaCreate) -> ParkingArea:
        geometry_json = json.dumps(payload.geom.model_dump())

        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            ST_IsValid(g)
                            AND NOT ST_IsEmpty(g)
                            AND ST_GeometryType(g) = 'ST_Polygon'
                        FROM (
                            SELECT ST_SetSRID(
                                ST_GeomFromGeoJSON(%s), 4326
                            ) AS g
                        ) AS geometry_check
                        """,
                        (geometry_json,),
                    )
                    if cursor.fetchone()[0] is not True:
                        raise InvalidParkingAreaGeometryError

                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))",
                        ("parking_area.parking_area_id",),
                    )
                    cursor.execute(
                        "SELECT COALESCE(MAX(parking_area_id), 0) + 1 "
                        "FROM parking_area"
                    )
                    parking_area_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        INSERT INTO parking_area (
                            parking_area_id, name, capacity, geom, created_at
                        )
                        VALUES (
                            %s, %s, %s,
                            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                            CURRENT_TIMESTAMP
                        )
                        RETURNING parking_area_id, name, capacity,
                                  ST_AsText(geom), created_at
                        """,
                        (
                            parking_area_id,
                            payload.name,
                            payload.capacity,
                            geometry_json,
                        ),
                    )
                    row = cursor.fetchone()
        except (
            psycopg2.errors.InvalidParameterValue,
            psycopg2.errors.InvalidTextRepresentation,
            psycopg2.errors.InternalError_,
        ) as exc:
            raise InvalidParkingAreaGeometryError from exc

        return ParkingArea(
            parking_area_id=row[0],
            name=row[1],
            capacity=row[2],
            geom=row[3],
            created_at=row[4],
        )

    @staticmethod
    def update_parking_area(
        conn: Any, parking_area_id: int, data: dict[str, Any]
    ) -> ParkingArea:
        if not data:
            raise ValueError("At least one field must be provided")

        updates: list[str] = []
        parameters: list[Any] = []

        if "name" in data:
            if data["name"] is None:
                raise ValueError("name cannot be null")
            updates.append("name = %s")
            parameters.append(data["name"])

        if "capacity" in data:
            if data["capacity"] is None:
                raise ValueError("capacity cannot be null")
            if data["capacity"] <= 0:
                raise ValueError("capacity must be greater than 0")
            updates.append("capacity = %s")
            parameters.append(data["capacity"])

        if "geom" in data:
            if data["geom"] is None:
                raise ValueError("geom cannot be null")
            geometry = data["geom"]
            if isinstance(geometry, GeoJSONPolygon):
                geometry = geometry.model_dump()
            geometry_json = json.dumps(geometry)
            updates.append(
                "geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)"
            )
            parameters.append(geometry_json)
        else:
            geometry_json = None

        try:
            with conn:
                with conn.cursor() as cursor:
                    if geometry_json is not None:
                        cursor.execute(
                            """
                            SELECT
                                ST_IsValid(g)
                                AND NOT ST_IsEmpty(g)
                                AND ST_GeometryType(g) = 'ST_Polygon'
                            FROM (
                                SELECT ST_SetSRID(
                                    ST_GeomFromGeoJSON(%s), 4326
                                ) AS g
                            ) AS geometry_check
                            """,
                            (geometry_json,),
                        )
                        if cursor.fetchone()[0] is not True:
                            raise InvalidParkingAreaGeometryError

                    parameters.append(parking_area_id)
                    cursor.execute(
                        f"""
                        UPDATE parking_area
                        SET {", ".join(updates)}
                        WHERE parking_area_id = %s
                        RETURNING parking_area_id, name, capacity,
                                  ST_AsText(geom), created_at
                        """,
                        parameters,
                    )
                    row = cursor.fetchone()

                    if row is None:
                        raise ParkingAreaNotFoundError
        except (
            psycopg2.errors.InvalidParameterValue,
            psycopg2.errors.InvalidTextRepresentation,
            psycopg2.errors.InternalError_,
        ) as exc:
            raise InvalidParkingAreaGeometryError from exc

        return ParkingArea(
            parking_area_id=row[0],
            name=row[1],
            capacity=row[2],
            geom=row[3],
            created_at=row[4],
        )

    # Gets all of the parking areas in the database
    def get_all_parking_areas(
        self, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM parking_area")
                count = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT parking_area_id, name, capacity, created_at
                    FROM parking_area
                    ORDER BY parking_area_id
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                rows = cursor.fetchall()
        finally:
            self.pool.putconn(conn)

        return {
            "items": [
                {
                    "parking_area_id": row[0],
                    "name": row[1],
                    "capacity": row[2],
                    "created_at": (
                        format_timestamp(row[3]) if row[3] is not None else None
                    ),
                }
                for row in rows
            ],
            "limit": limit,
            "offset": offset,
            "count": count,
        }

    def get_parking_areas(
        self,
        name: str | None,
        bbox: list[float] | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        filters: list[str] = []
        parameters: list[Any] = []

        if name is not None:
            filters.append("name = %s")
            parameters.append(name)

        if bbox is not None:
            filters.append(
                "ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
            )
            parameters.extend(bbox)

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) FROM parking_area {where_clause}",
                    parameters,
                )
                count = cursor.fetchone()[0]
                cursor.execute(
                    f"""
                    SELECT parking_area_id, name, capacity, created_at
                    FROM parking_area
                    {where_clause}
                    ORDER BY parking_area_id
                    LIMIT %s OFFSET %s
                    """,
                    [*parameters, limit, offset],
                )
                rows = cursor.fetchall()
        finally:
            self.pool.putconn(conn)

        return {
            "items": [
                {
                    "parking_area_id": row[0],
                    "name": row[1],
                    "capacity": row[2],
                    "created_at": (
                        format_timestamp(row[3]) if row[3] is not None else None
                    ),
                }
                for row in rows
            ],
            "limit": limit,
            "offset": offset,
            "count": count,
        }
    
    def get_parking_area_by_id(self, parking_area_id: int) -> ParkingArea | None:
        conn = self.pool.getconn() # Get a connection from the pool
        cursor = conn.cursor() # Create a cursor to execute the query
        query = """
                SELECT parking_area_id, name, capacity, ST_AsText(geom), created_at
                FROM parking_area
                WHERE parking_area_id = %s
                """
        cursor.execute(query, (parking_area_id,)) # Execute the query and stores the result in the cursor
        row = cursor.fetchone() # Fetches the first row of the result set

        if row is None:
            cursor.close() # Close the cursor
            self.pool.putconn(conn) # Return the connection to the pool
            print("Does not exist")
            return None
        
        parking_area = ParkingArea(
            parking_area_id=row[0],
            name=row[1],
            capacity=row[2],
            geom=row[3],
            created_at=row[4]
        )
        
        cursor.close() # Close the cursor
        self.pool.putconn(conn) # Return the connection to the pool
        print("Does exist")
        return parking_area
    
    def delete_parking_area_by_id(self, parking_area_id: int) -> bool:
        conn = self.pool.getconn() # Get a connection from the pool
        cursor = conn.cursor() # Create a cursor to execute the query
        query = """
                DELETE FROM parking_area
                WHERE parking_area_id = %s
                """
        cursor.execute(query, (parking_area_id,)) # Execute the query and stores the result in the cursor
        rows_affected = cursor.rowcount # Get the number of rows affected by the delete operation
        
        conn.commit() # Commit the transaction to make the deletion permanent
        cursor.close() # Close the cursor
        self.pool.putconn(conn) # Return the connection to the pool
        print("Deleted")
        return rows_affected == 1