from __future__ import annotations

from typing import Any
from api.v1.config.dbconfig import PG_DB_CONFIG, POOL_CONFIG
import psycopg2
from datetime import datetime
from pydantic import BaseModel, Field
from psycopg2.pool import SimpleConnectionPool

# These are the attributes of the ParkingArea table in the database
class ParkingArea(BaseModel):
    parking_area_id: int
    name: str
    capacity: int
    geom: str
    created_at: datetime

class ParkingAreaDAO():
    def __init__(self):
        self.pool = SimpleConnectionPool(POOL_CONFIG["minconn"], POOL_CONFIG["maxconn"], **PG_DB_CONFIG)

    def get_all_parking_areas(self) -> tuple[list[ParkingArea], int]:
        conn = self.pool.getconn()
        cursor = conn.cursor()
        query = """
                SELECT parking_area_id, name, capacity, ST_AsText(geom), created_at
                FROM parking_area
                """
        cursor.execute(query)
        result : list[ParkingArea] = []
        for row in cursor:
            result.append(ParkingArea(
                parking_area_id=row[0],
                name=row[1],
                capacity=row[2],
                geom=row[3],
                created_at=row[4]
            ))
        
        cursor.close()
        self.pool.putconn(conn)
        return result